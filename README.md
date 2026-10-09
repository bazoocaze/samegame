# SameGame

Clone do SameGame (Clickomania) em **um único arquivo HTML**, sem dependências.

```
same_game/
├── index.html            # o jogo
├── pyproject.toml        # playwright (uv venv)
├── scripts/
│   ├── play.py           # playthrough automatizado (imprime o tabuleiro)
│   └── screenshot.py     # captura de tela do jogo
└── tests/
    ├── browser_lib.py    # helpers reaproveitáveis (Chrome via CDP)
    ├── test_game.py      # teste black-box no browser
    ├── logic_test.js     # teste de lógica determinístico (sem browser)
    └── screenshot.png
```

## Regras

- Clique num grupo de **2+ blocos** da mesma cor (adjacência orthogonal) para removê-lo.
- Blocos caem; colunas vazias deslizam para a esquerda.
- Pontos por grupo de `n`: `n × (n − 1)`. Tabuleiro limpo: `+2000`.
- Recorde por tamanho/cores fica em `localStorage`.

Extras: undo, hint (melhor grupo), shuffle, som (WebAudio), hover com badge de pontos,
animações de pop/queda, teclado `N U H S M`.

## Rodar

Abra `index.html` no navegador.

## Testes

Usa o Chrome já instalado via CDP (skill `browser-control`) — não baixa navegador.

```bash
uv venv && uv pip install playwright

node tests/logic_test.js          # invariants de gravidade/colunas, score, undo, shuffle
uv run python tests/test_game.py  # joga o jogo pelo browser e confere HUD + render + persistência
uv run python scripts/play.py --moves 40 --delay 0.4
uv run python scripts/screenshot.py --moves 14 --out tests/screenshot.png
```

Notas do harness:
- `tests/browser_lib.py` expõe `open_game`, `read_state`, `read_grid`, `hud`, `click_cell`,
  `cell_geometry`, `wait_idle`, `settle`, `largest_group`, `check_invariants`.
- `wait_idle`/`settle` dormem em vez de fazer polling apertado (não martela a CPU).
- O jogo expõe `window.samegame` (hook de teste) para ler o estado sem amostrar pixels.
- A aba precisa estar em foreground (`bring_to_front`), senão o Chrome throttles `requestAnimationFrame`
  e o loop de render para.

Bugs encontrados pelos testes: `rgb()` recebia entradas `{name, hex}` do palette (blocos cinzas)
e `endGame()` não disparava quando só restavam grupos de tamanho 1.
