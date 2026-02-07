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
    └── splitwiser.html       # Bill splitter (Mode A: solo JS, Mode B: SocketIO rooms)
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

## Notes
- SocketIO rooms stored in memory (1 worker only). For scaling, would need Redis.
- Free Render tier sleeps after 15 min inactivity.
