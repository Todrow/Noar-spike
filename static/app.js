const wsProtocol = location.protocol === "https:" ? "wss" : "ws";
const ws = new WebSocket(`${wsProtocol}://${location.host}/ws`);

const state = {
  playerId: null,
  board: [],
  players: [],
  eventLog: [],
  winner: null,
  me: null,
  winScore: 3,
  turnPlayerId: null,
  turnPlayerName: null,
  isMyTurn: false,
  selectedCardName: null,
  lastAction: null,
  actionSeq: 0,
  animatedSeq: 0,
  pendingAnimation: null,
};

const el = {
  joinSection: document.getElementById("joinSection"),
  meSection: document.getElementById("meSection"),
  actionsSection: document.getElementById("actionsSection"),
  nameInput: document.getElementById("nameInput"),
  joinBtn: document.getElementById("joinBtn"),
  meName: document.getElementById("meName"),
  meScore: document.getElementById("meScore"),
  meLocation: document.getElementById("meLocation"),
  turnLabel: document.getElementById("turnLabel"),
  playersList: document.getElementById("playersList"),
  board: document.getElementById("board"),
  logList: document.getElementById("logList"),
  winnerLabel: document.getElementById("winnerLabel"),
  targetCardInput: document.getElementById("targetCardInput"),
  killBtn: document.getElementById("killBtn"),
  interrogateBtn: document.getElementById("interrogateBtn"),
  rowIndexInput: document.getElementById("rowIndexInput"),
  rowDirectionSelect: document.getElementById("rowDirectionSelect"),
  shiftRowBtn: document.getElementById("shiftRowBtn"),
  colIndexInput: document.getElementById("colIndexInput"),
  colDirectionSelect: document.getElementById("colDirectionSelect"),
  shiftColBtn: document.getElementById("shiftColBtn"),
  toast: document.getElementById("toast"),
};

let toastTimer = null;

function setActionsEnabled(enabled) {
  const controls = [
    el.targetCardInput,
    el.killBtn,
    el.interrogateBtn,
    el.rowIndexInput,
    el.rowDirectionSelect,
    el.shiftRowBtn,
    el.colIndexInput,
    el.colDirectionSelect,
    el.shiftColBtn,
  ];
  controls.forEach((control) => {
    control.disabled = !enabled;
  });
}

function send(payload) {
  if (ws.readyState !== WebSocket.OPEN) {
    showToast("Нет соединения с сервером.");
    return;
  }
  ws.send(JSON.stringify(payload));
}

function showToast(message) {
  el.toast.textContent = message;
  el.toast.classList.add("show");
  if (toastTimer) {
    clearTimeout(toastTimer);
  }
  toastTimer = setTimeout(() => {
    el.toast.classList.remove("show");
  }, 2200);
}

function cardIsAdjacentOrSelf(cardName) {
  if (!state.me || !state.board.length) {
    return false;
  }
  let mePos = null;
  let targetPos = null;

  for (let r = 0; r < state.board.length; r += 1) {
    for (let c = 0; c < state.board[r].length; c += 1) {
      if (state.board[r][c] === state.me.locationName) {
        mePos = [r, c];
      }
      if (state.board[r][c] === cardName) {
        targetPos = [r, c];
      }
    }
  }

  if (!mePos || !targetPos) {
    return false;
  }

  return Math.abs(mePos[0] - targetPos[0]) <= 1 && Math.abs(mePos[1] - targetPos[1]) <= 1;
}

function render() {
  el.playersList.innerHTML = "";
  state.players
    .slice()
    .sort((a, b) => b.score - a.score || a.name.localeCompare(b.name, "ru"))
    .forEach((p) => {
      const li = document.createElement("li");
      li.textContent = `${p.name}: ${p.score}`;
      el.playersList.appendChild(li);
    });

  el.board.innerHTML = "";
  state.board.forEach((row, rowIndex) => {
    row.forEach((cardName, colIndex) => {
      const div = document.createElement("div");
      div.className = "cell";
      div.textContent = cardName;
      if (state.selectedCardName === cardName) {
        div.classList.add("selected");
      }
      if (state.me && cardName === state.me.locationName) {
        div.classList.add("me");
      }

      const anim = state.pendingAnimation;
      if (anim) {
        if (anim.type === "shift_row" && rowIndex === anim.index) {
          div.classList.add(anim.direction === "right" ? "anim-from-left" : "anim-from-right");
        } else if (anim.type === "shift_col" && colIndex === anim.index) {
          div.classList.add(anim.direction === "down" ? "anim-from-top" : "anim-from-bottom");
        } else if (anim.type === "kill" && cardName === anim.target) {
          div.classList.add(anim.hit ? "anim-kill-hit" : "anim-kill-miss");
        } else if (anim.type === "interrogate") {
          let targetPos = null;
          for (let r = 0; r < state.board.length; r += 1) {
            for (let c = 0; c < state.board[r].length; c += 1) {
              if (state.board[r][c] === anim.target) {
                targetPos = [r, c];
              }
            }
          }
          if (
            targetPos &&
            Math.abs(rowIndex - targetPos[0]) <= 1 &&
            Math.abs(colIndex - targetPos[1]) <= 1
          ) {
            div.classList.add("anim-interrogate");
          }
        }
      }

      div.addEventListener("click", () => {
        state.selectedCardName = cardName;
        el.targetCardInput.value = cardName;
        el.rowIndexInput.value = String(rowIndex + 1);
        el.colIndexInput.value = String(colIndex + 1);
        render();
      });
      el.board.appendChild(div);
    });
  });

  el.logList.innerHTML = "";
  state.eventLog
    .slice()
    .reverse()
    .forEach((entry) => {
      const li = document.createElement("li");
      li.textContent = entry;
      el.logList.appendChild(li);
    });

  if (state.me) {
    el.joinSection.classList.add("hidden");
    el.meSection.classList.remove("hidden");
    el.actionsSection.classList.remove("hidden");
    el.meName.textContent = state.me.name;
    el.meScore.textContent = String(state.me.score);
    el.meLocation.textContent = state.me.locationName;

    if (state.winner) {
      el.turnLabel.textContent = "Игра завершена";
      setActionsEnabled(false);
    } else if (state.turnPlayerName) {
      if (state.isMyTurn) {
        el.turnLabel.textContent = "Ваш";
        setActionsEnabled(true);
      } else {
        el.turnLabel.textContent = `Игрок ${state.turnPlayerName}`;
        setActionsEnabled(false);
      }
    } else {
      el.turnLabel.textContent = "Ожидание игроков";
      setActionsEnabled(false);
    }
  }

  if (state.winner) {
    el.winnerLabel.textContent = `Победитель: ${state.winner} (до ${state.winScore} очков)`;
  } else {
    el.winnerLabel.textContent = "";
  }
}

ws.addEventListener("open", () => {
  showToast("Соединение установлено.");
});

ws.addEventListener("close", () => {
  showToast("Соединение закрыто.");
});

ws.addEventListener("message", (event) => {
  let data;
  try {
    data = JSON.parse(event.data);
  } catch {
    showToast("Сервер прислал некорректные данные.");
    return;
  }

  if (data.type === "error") {
    showToast(data.message || "Ошибка на сервере.");
    return;
  }

  if (data.type === "joined") {
    state.playerId = data.playerId;
    return;
  }

  if (data.type === "state") {
    state.board = data.state.board || [];
    state.players = data.state.players || [];
    state.eventLog = data.state.eventLog || [];
    state.winner = data.state.winner || null;
    state.winScore = data.state.winScore || 3;
    state.turnPlayerId = data.state.turnPlayerId || null;
    state.turnPlayerName = data.state.turnPlayerName || null;
    state.isMyTurn = Boolean(data.state.isMyTurn);
    state.me = data.state.me || null;

    const newSeq = data.state.actionSeq || 0;
    if (newSeq > state.animatedSeq && data.state.lastAction) {
      state.pendingAnimation = data.state.lastAction;
      state.animatedSeq = newSeq;
    } else {
      state.pendingAnimation = null;
      if (newSeq > state.animatedSeq) {
        state.animatedSeq = newSeq;
      }
    }
    state.lastAction = data.state.lastAction || null;
    state.actionSeq = newSeq;

    render();
  }
});

el.joinBtn.addEventListener("click", () => {
  const name = el.nameInput.value.trim();
  if (!name) {
    showToast("Введите имя игрока.");
    return;
  }
  send({ type: "join", name });
});

el.nameInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    el.joinBtn.click();
  }
});

el.killBtn.addEventListener("click", () => {
  if (!state.isMyTurn) {
    showToast("Сейчас не ваш ход.");
    return;
  }
  const target = el.targetCardInput.value.trim();
  if (!target) {
    showToast("Укажите карту-цель.");
    return;
  }
  if (!cardIsAdjacentOrSelf(target) || target === state.me?.locationName) {
    showToast("Для атаки нужна соседняя карта (не своя). ");
    return;
  }
  send({ type: "action", action: "kill", target });
});

el.interrogateBtn.addEventListener("click", () => {
  if (!state.isMyTurn) {
    showToast("Сейчас не ваш ход.");
    return;
  }
  const target = el.targetCardInput.value.trim();
  if (!target) {
    showToast("Укажите карту для допроса.");
    return;
  }
  if (!cardIsAdjacentOrSelf(target)) {
    showToast("Для допроса нужна своя или соседняя карта.");
    return;
  }
  send({ type: "action", action: "interrogate", target });
});

el.shiftRowBtn.addEventListener("click", () => {
  if (!state.isMyTurn) {
    showToast("Сейчас не ваш ход.");
    return;
  }
  const index = Number(el.rowIndexInput.value);
  const direction = el.rowDirectionSelect.value;
  if (!Number.isInteger(index) || index < 1 || index > 7) {
    showToast("Номер строки должен быть от 1 до 7.");
    return;
  }
  send({ type: "action", action: "shift_row", index, direction });
});

el.shiftColBtn.addEventListener("click", () => {
  if (!state.isMyTurn) {
    showToast("Сейчас не ваш ход.");
    return;
  }
  const index = Number(el.colIndexInput.value);
  const direction = el.colDirectionSelect.value;
  if (!Number.isInteger(index) || index < 1 || index > 7) {
    showToast("Номер колонки должен быть от 1 до 7.");
    return;
  }
  send({ type: "action", action: "shift_col", index, direction });
});
