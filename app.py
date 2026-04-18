from __future__ import annotations

import asyncio
import json
import random
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


BOARD_SIZE = 7
WIN_SCORE = 3
LOCATION_NAMES = [
    "Аэропорт",
    "Банк",
    "Библиотека",
    "Больница",
    "Вокзал",
    "Гараж",
    "Гостиница",
    "Дача",
    "Завод",
    "Заправка",
    "Зоопарк",
    "Кафе",
    "Кинотеатр",
    "Клуб",
    "Колледж",
    "Лаборатория",
    "Лес",
    "Магазин",
    "Маяк",
    "Музей",
    "Набережная",
    "Офис",
    "Парк",
    "Пекарня",
    "Порт",
    "Почта",
    "Пристань",
    "Ратуша",
    "Ресторан",
    "Рынок",
    "Склад",
    "Сквер",
    "Станция",
    "Стадион",
    "Театр",
    "Тюрьма",
    "Университет",
    "Фабрика",
    "Ферма",
    "Храм",
    "Цирк",
    "Шахта",
    "Школа",
    "Штаб",
    "Электростанция",
    "Яхт-клуб",
    "Мастерская",
    "Серверная",
    "Обсерватория",
]


@dataclass
class Player:
    player_id: str
    name: str
    location_name: str
    score: int = 0


@dataclass
class GameRoom:
    board: list[list[str]] = field(default_factory=list)
    players: dict[str, Player] = field(default_factory=dict)
    turn_order: list[str] = field(default_factory=list)
    turn_index: int = 0
    event_log: list[str] = field(default_factory=list)
    winner_id: str | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def __post_init__(self) -> None:
        if not self.board:
            self.reset_board()

    def reset_board(self) -> None:
        names = LOCATION_NAMES.copy()
        random.shuffle(names)
        self.board = [
            names[row * BOARD_SIZE : (row + 1) * BOARD_SIZE] for row in range(BOARD_SIZE)
        ]
        
        # Переназначаем уникальные местоположения для всех игроков
        for player in self.players.values():
            available_locations = [loc for loc in names if loc not in {p.location_name for p in self.players.values() if p != player}]
            if available_locations:
                player.location_name = random.choice(available_locations)
                names.remove(player.location_name)
            else:
                player.location_name = random.choice(LOCATION_NAMES)
                
        self.turn_order.clear()
        self.turn_index = 0
        self.event_log.clear()
        self.winner_id = None

    def card_to_coord(self, card_name: str) -> tuple[int, int] | None:
        for r, row in enumerate(self.board):
            for c, value in enumerate(row):
                if value == card_name:
                    return (r, c)
        return None

    def player_coord(self, player: Player) -> tuple[int, int] | None:
        return self.card_to_coord(player.location_name)

    def random_location(self) -> str:
        return random.choice(LOCATION_NAMES)

    def unique_random_location(self) -> str:
        occupied_locations = {player.location_name for player in self.players.values()}
        available_locations = [loc for loc in LOCATION_NAMES if loc not in occupied_locations]
        if not available_locations:
            # Если все локации заняты, возвращаем случайную (это может произойти только если
            # игроков больше чем уникальных локаций, что маловероятно)
            return random.choice(LOCATION_NAMES)
        return random.choice(available_locations)

    def append_event(self, message: str) -> None:
        self.event_log.append(message)
        if len(self.event_log) > 20:
            self.event_log = self.event_log[-20:]

    def is_adjacent_or_same(
        self, origin: tuple[int, int], target: tuple[int, int], include_same: bool
    ) -> bool:
        row_distance = abs(origin[0] - target[0])
        col_distance = abs(origin[1] - target[1])
        if row_distance > 1 or col_distance > 1:
            return False
        if not include_same and row_distance == 0 and col_distance == 0:
            return False
        return True

    def coords_in_radius_1(self, center: tuple[int, int]) -> set[tuple[int, int]]:
        coords: set[tuple[int, int]] = set()
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                nr = center[0] + dr
                nc = center[1] + dc
                if 0 <= nr < BOARD_SIZE and 0 <= nc < BOARD_SIZE:
                    coords.add((nr, nc))
        return coords

    def shift_row(self, row_index: int, direction: int) -> None:
        row = self.board[row_index]
        if direction > 0:
            self.board[row_index] = [row[-1]] + row[:-1]
        else:
            self.board[row_index] = row[1:] + [row[0]]

    def shift_col(self, col_index: int, direction: int) -> None:
        column = [self.board[r][col_index] for r in range(BOARD_SIZE)]
        if direction > 0:
            shifted = [column[-1]] + column[:-1]
        else:
            shifted = column[1:] + [column[0]]
        for r in range(BOARD_SIZE):
            self.board[r][col_index] = shifted[r]

    def public_players(self) -> list[dict[str, Any]]:
        return [
            {
                "id": p.player_id,
                "name": p.name,
                "score": p.score,
            }
            for p in self.players.values()
        ]

    def winner_name(self) -> str | None:
        if self.winner_id and self.winner_id in self.players:
            return self.players[self.winner_id].name
        return None

    def current_turn_player_id(self) -> str | None:
        if not self.turn_order:
            return None
        if self.turn_index >= len(self.turn_order):
            self.turn_index = 0
        return self.turn_order[self.turn_index]

    def current_turn_player_name(self) -> str | None:
        pid = self.current_turn_player_id()
        if pid and pid in self.players:
            return self.players[pid].name
        return None

    def advance_turn(self) -> None:
        if not self.turn_order:
            self.turn_index = 0
            return
        self.turn_index = (self.turn_index + 1) % len(self.turn_order)

    def remove_player(self, player_id: str) -> Player | None:
        departed = self.players.pop(player_id, None)
        if departed is None:
            return None

        try:
            removed_index = self.turn_order.index(player_id)
        except ValueError:
            removed_index = None
        else:
            self.turn_order.pop(removed_index)

            if not self.turn_order:
                self.turn_index = 0
            elif removed_index < self.turn_index:
                self.turn_index -= 1
            elif removed_index == self.turn_index and self.turn_index >= len(self.turn_order):
                self.turn_index = 0

        if self.winner_id == player_id:
            self.winner_id = None

        return departed

    def state_for(self, player_id: str | None) -> dict[str, Any]:
        me = self.players.get(player_id) if player_id else None
        turn_player_id = self.current_turn_player_id()
        return {
            "board": self.board,
            "players": self.public_players(),
            "eventLog": self.event_log,
            "winner": self.winner_name(),
            "winScore": WIN_SCORE,
            "turnPlayerId": turn_player_id,
            "turnPlayerName": self.current_turn_player_name(),
            "isMyTurn": bool(me and turn_player_id and me.player_id == turn_player_id),
            "me": {
                "id": me.player_id,
                "name": me.name,
                "score": me.score,
                "locationName": me.location_name,
            }
            if me
            else None,
        }


app = FastAPI(title="Spy LAN")
room = GameRoom()
connections: dict[WebSocket, str | None] = {}
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(static_dir / "index.html")


async def send_state_to_all() -> None:
    stale: list[WebSocket] = []
    for ws, pid in list(connections.items()):
        try:
            await ws.send_json({"type": "state", "state": room.state_for(pid)})
        except Exception:
            stale.append(ws)
    for ws in stale:
        connections.pop(ws, None)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    connections[websocket] = None
    await websocket.send_json({"type": "state", "state": room.state_for(None)})

    try:
        while True:
            raw = await websocket.receive_text()
            payload = json.loads(raw)
            msg_type = payload.get("type")

            if msg_type == "join":
                await handle_join(websocket, payload)
                continue

            if msg_type == "action":
                await handle_action(websocket, payload)
                continue

            await websocket.send_json({"type": "error", "message": "Неизвестный тип сообщения."})
    except WebSocketDisconnect:
        pass
    finally:
        pid = connections.pop(websocket, None)
        if pid and pid in room.players:
            async with room.lock:
                departed = room.remove_player(pid)
                if departed is not None:
                    room.append_event(f"{departed.name} покинул игру.")
                    if room.players and not room.winner_id:
                        next_name = room.current_turn_player_name()
                        if next_name:
                            room.append_event(f"Теперь ход: {next_name}.")
            await send_state_to_all()


async def handle_join(websocket: WebSocket, payload: dict[str, Any]) -> None:
    name = str(payload.get("name", "")).strip()
    if not name:
        await websocket.send_json({"type": "error", "message": "Введите имя."})
        return

    async with room.lock:
        player_id = uuid.uuid4().hex
        location_name = room.unique_random_location()
        room.players[player_id] = Player(
            player_id=player_id,
            name=name[:30],
            location_name=location_name,
        )
        room.turn_order.append(player_id)
        connections[websocket] = player_id
        room.append_event(f"{name[:30]} присоединился к игре.")
        if len(room.turn_order) == 1:
            room.append_event(f"Первый ход: {name[:30]}.")

    await websocket.send_json({"type": "joined", "playerId": player_id})
    await send_state_to_all()


async def handle_action(websocket: WebSocket, payload: dict[str, Any]) -> None:
    actor_id = connections.get(websocket)
    if not actor_id or actor_id not in room.players:
        await websocket.send_json({"type": "error", "message": "Сначала войдите в игру."})
        return

    action = payload.get("action")

    async with room.lock:
        actor = room.players[actor_id]
        if room.winner_id:
            await websocket.send_json(
                {
                    "type": "error",
                    "message": "Игра уже завершена. Обновите страницу для новой партии.",
                }
            )
            return

        current_turn_id = room.current_turn_player_id()
        if current_turn_id != actor.player_id:
            turn_name = room.current_turn_player_name() or "другого игрока"
            await websocket.send_json(
                {
                    "type": "error",
                    "message": f"Сейчас ход {turn_name}.",
                }
            )
            return

        if action == "kill":
            error = process_kill(actor, payload)
            if error:
                await websocket.send_json({"type": "error", "message": error})
                return

        elif action == "interrogate":
            error = process_interrogate(actor, payload)
            if error:
                await websocket.send_json({"type": "error", "message": error})
                return

        elif action == "shift_row":
            error = process_shift_row(actor, payload)
            if error:
                await websocket.send_json({"type": "error", "message": error})
                return

        elif action == "shift_col":
            error = process_shift_col(actor, payload)
            if error:
                await websocket.send_json({"type": "error", "message": error})
                return

        else:
            await websocket.send_json({"type": "error", "message": "Неизвестное действие."})
            return

        if not room.winner_id:
            room.advance_turn()
            next_name = room.current_turn_player_name()
            if next_name:
                room.append_event(f"Ход переходит к игроку {next_name}.")

    await send_state_to_all()


def process_kill(actor: Player, payload: dict[str, Any]) -> str | None:
    target_card = str(payload.get("target", "")).strip()
    if not target_card:
        return "Для действия 'убить' нужно указать карту-цель."

    actor_coord = room.player_coord(actor)
    target_coord = room.card_to_coord(target_card)
    if actor_coord is None or target_coord is None:
        return "Не удалось определить позицию карты."

    if not room.is_adjacent_or_same(actor_coord, target_coord, include_same=False):
        return "Можно атаковать только соседнюю карту."

    possible_victims = [
        p
        for p in room.players.values()
        if p.player_id != actor.player_id and p.location_name == target_card
    ]

    if not possible_victims:
        room.append_event(f"{actor.name} атаковал карту '{target_card}', но никого не нашел.")
        return None

    victim = random.choice(possible_victims)
    actor.score += 1
    room.append_event(f"{actor.name} вскрыл {victim.name} и получил 1 очко.")

    victim.location_name = room.unique_random_location()
    room.append_event(f"{victim.name} получил новую карту местоположения.")

    if actor.score >= WIN_SCORE:
        room.winner_id = actor.player_id
        room.append_event(f"{actor.name} победил. Набрано {actor.score} очка(ов).")

    return None


def process_interrogate(actor: Player, payload: dict[str, Any]) -> str | None:
    target_card = str(payload.get("target", "")).strip()
    if not target_card:
        return "Для допроса нужно указать карту."

    actor_coord = room.player_coord(actor)
    target_coord = room.card_to_coord(target_card)
    if actor_coord is None or target_coord is None:
        return "Не удалось определить позицию карты."

    if not room.is_adjacent_or_same(actor_coord, target_coord, include_same=True):
        return "Для допроса можно выбрать свою карту или соседнюю."

    area = room.coords_in_radius_1(target_coord)
    raised = []

    for p in room.players.values():
        coord = room.player_coord(p)
        if coord and coord in area:
            raised.append(p.name)

    if raised:
        room.append_event(
            f"{actor.name} провел допрос у '{target_card}'. Подняли руки: {', '.join(raised)}."
        )
    else:
        room.append_event(f"{actor.name} провел допрос у '{target_card}', но никто не поднял руку.")

    return None


def process_shift_row(actor: Player, payload: dict[str, Any]) -> str | None:
    try:
        row_index = int(payload.get("index"))
    except (TypeError, ValueError):
        return "Номер строки должен быть целым числом от 1 до 7."

    if not 1 <= row_index <= BOARD_SIZE:
        return "Номер строки должен быть от 1 до 7."

    direction = str(payload.get("direction", "right")).lower()
    if direction not in {"left", "right"}:
        return "Направление сдвига строки: left или right."

    room.shift_row(row_index - 1, 1 if direction == "right" else -1)
    room.append_event(f"{actor.name} сдвинул строку {row_index} ({direction}).")
    return None


def process_shift_col(actor: Player, payload: dict[str, Any]) -> str | None:
    try:
        col_index = int(payload.get("index"))
    except (TypeError, ValueError):
        return "Номер колонки должен быть целым числом от 1 до 7."

    if not 1 <= col_index <= BOARD_SIZE:
        return "Номер колонки должен быть от 1 до 7."

    direction = str(payload.get("direction", "down")).lower()
    if direction not in {"up", "down"}:
        return "Направление сдвига колонки: up или down."

    room.shift_col(col_index - 1, 1 if direction == "down" else -1)
    room.append_event(f"{actor.name} сдвинул колонку {col_index} ({direction}).")
    return None


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
