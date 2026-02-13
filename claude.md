# FunTookit

A cute daily toolkit web app with useful little tools. Flask + SocketIO, deployed on Render.com.

## Tech Stack
- **Backend**: Flask + Flask-SocketIO
- **Frontend**: Vanilla HTML/CSS/JS, HTML5 Canvas
- **Deploy**: Render.com free tier (gunicorn + gevent-websocket)

## Visual Style
- Warm seashell background (`#FFF5EE`), white rounded panels, soft shadows
- Cute, smooth, consistent across all tools
- Each tool has its own accent color
- Font: Segoe UI, buttons with hover scale effect

## File Structure
```
FunTookit/
├── app.py                    # Server: TOOLS registry, routes, SocketIO events
├── requirements.txt
├── render.yaml
├── DEPLOY.md
├── claude.md                 # This file
└── templates/
    ├── home.html             # Tool card grid (auto-rendered from TOOLS list)
    ├── decision_roller.html  # Spinning wheel (all client-side)
    ├── splitwiser.html       # Bill splitter (Mode A: solo JS, Mode B: SocketIO rooms)
    └── spy_painter.html      # Multiplayer draw-and-guess game (SocketIO rooms)
```

## How to Add a New Tool
1. Add an entry to `TOOLS` list in `app.py`:
   ```python
   {'id': 'my_tool', 'name': 'My Tool', 'icon': '\U0001fxxx', 'desc': '...', 'color': '#XXX'}
   ```
2. Add a route in `app.py`:
   ```python
   @app.route('/my_tool')
   def my_tool():
       return render_template('my_tool.html')
   ```
3. Create `templates/my_tool.html` (copy an existing tool as starting template)

Home page auto-renders cards from the TOOLS list via Jinja loop.

## Current Tools

### 1. Decision Roller (accent: `#FF9EB5`)
- Add choices as colored chips, remove with X
- HTML5 Canvas spinning wheel with colored segments
- Animation: `requestAnimationFrame` with ease-out cubic (~4s)
- Confetti celebration on result
- Entirely client-side, no server needed

### 2. Splitwiser (accent: `#78C8A0`)
- **Mode A (Solo)**: All client-side JS
  - Add people (name, personal cost, amount paid) -> calculate
  - Total cost = sum of all amount_paid (auto-computed)
- **Mode B (Room)**: SocketIO
  - Host creates room -> others join with 4-letter code -> each submits own data -> host triggers calculate -> server broadcasts results
- **Algorithm** (same logic in JS and Python):
  1. Pro-rate personal costs if sum != total_cost
  2. Balance = amount_paid - adjusted_cost
  3. Greedy settlement: match biggest debtor to biggest creditor, minimize transactions

### 3. Spy Painter (accent: `#C9A0DC`)
Real-time multiplayer draw-and-guess game via SocketIO. Min 3 players, max 8.

- **Game Flow** (per round):
  1. One player is secretly assigned as the **Spy**
  2. Non-spy players suggest and vote on a word to draw
  3. Spy sees rejected words but **not** the chosen one
  4. Everyone takes turns drawing (including the spy, who must fake it)
  5. Each player draws **twice** (2 passes)
  6. All drawings shown in a gallery; players vote on who is the spy

- **Scoring**:
  - Spy caught: non-spy players get **1 pt** each, correct voters get **+2 pts**
  - Spy escapes: spy gets **3 pts**
  - Spy selection rotates to avoid repeats

- **Drawing Tools**: Pen, Line, Rectangle, Circle, Fill (flood fill), Eraser
- **Features**: 16-color palette, 4 width sizes, undo, clear, touch support
- **Canvas**: Fixed 600x400 internal resolution, CSS-scaled for responsiveness
- **Server events**: `sp_` prefix (e.g. `sp_create_room`, `sp_stroke`, `sp_vote_spy`)
- **Disconnect handling**: If a player disconnects mid-game, round ends and returns to lobby

## Notes
- SocketIO rooms stored in memory (1 worker only). For scaling, would need Redis.
- Free Render tier sleeps after 15 min inactivity.
