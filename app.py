import socket
import random
import string
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room as sio_join

app = Flask(__name__)
app.secret_key = 'funtookit-secret'
socketio = SocketIO(app, cors_allowed_origins="*")

# ---------------------------------------------------------------------------
# TOOLS registry – add a new tool here, create a route + template, done!
# ---------------------------------------------------------------------------
TOOLS = [
    {
        'id': 'decision_roller',
        'name': 'Decision Roller',
        'icon': '\U0001f3b2',
        'desc': 'Can\'t decide? Spin the wheel and let fate choose for you!',
        'color': '#FF9EB5',
    },
    {
        'id': 'splitwiser',
        'name': 'Splitwiser',
        'icon': '\U0001f4b0',
        'desc': 'Split bills fairly among friends. Solo or room mode!',
        'color': '#78C8A0',
    },
]

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route('/')
def home():
    return render_template('home.html', tools=TOOLS)


@app.route('/decision_roller')
def decision_roller():
    return render_template('decision_roller.html')


@app.route('/splitwiser')
def splitwiser():
    return render_template('splitwiser.html')


# ---------------------------------------------------------------------------
# Splitwiser Mode B – SocketIO room logic
# ---------------------------------------------------------------------------
rooms = {}
sid_to_room = {}


def gen_code():
    return ''.join(random.choices(string.ascii_uppercase, k=4))


def calculate_settlements(total_cost, people):
    """
    people: list of {name, personal_cost, amount_paid}
    Returns {adjusted: [{name, adjusted_cost, amount_paid, balance}], settlements: [{from, to, amount}]}
    """
    # 1. Pro-rate personal costs if sum != total_cost
    raw_sum = sum(p['personal_cost'] for p in people)
    if raw_sum == 0:
        # Equal split fallback
        share = total_cost / len(people)
        adjusted = [{'name': p['name'], 'adjusted_cost': round(share, 2),
                      'amount_paid': p['amount_paid'],
                      'balance': round(p['amount_paid'] - share, 2)} for p in people]
    else:
        ratio = total_cost / raw_sum
        adjusted = []
        for p in people:
            adj = round(p['personal_cost'] * ratio, 2)
            adjusted.append({
                'name': p['name'],
                'adjusted_cost': adj,
                'amount_paid': p['amount_paid'],
                'balance': round(p['amount_paid'] - adj, 2),
            })

    # 2. Greedy settlement – minimize transactions
    balances = [{'name': a['name'], 'balance': a['balance']} for a in adjusted]
    settlements = []
    while True:
        # Separate debtors (negative balance) and creditors (positive balance)
        debtors = sorted([b for b in balances if b['balance'] < -0.005], key=lambda x: x['balance'])
        creditors = sorted([b for b in balances if b['balance'] > 0.005], key=lambda x: -x['balance'])
        if not debtors or not creditors:
            break
        d = debtors[0]
        c = creditors[0]
        amt = round(min(-d['balance'], c['balance']), 2)
        settlements.append({'from': d['name'], 'to': c['name'], 'amount': amt})
        d['balance'] = round(d['balance'] + amt, 2)
        c['balance'] = round(c['balance'] - amt, 2)

    return {'adjusted': adjusted, 'settlements': settlements}


@socketio.on('sw_create_room')
def on_sw_create(data):
    sid = request.sid
    host_name = data.get('name', '').strip()
    if not host_name:
        return emit('sw_error', {'msg': 'Please enter your name'})
    code = gen_code()
    while code in rooms:
        code = gen_code()
    rooms[code] = {
        'host_sid': sid,
        'members': [{'sid': sid, 'name': host_name, 'data': None}],
    }
    sid_to_room[sid] = code
    sio_join(code)
    emit('sw_room_created', {'code': code, 'name': host_name})


@socketio.on('sw_join_room')
def on_sw_join(data):
    sid = request.sid
    name = data.get('name', '').strip()
    code = data.get('code', '').strip().upper()
    if not name:
        return emit('sw_error', {'msg': 'Please enter your name'})
    if code not in rooms:
        return emit('sw_error', {'msg': 'Room not found'})
    room = rooms[code]
    # Check duplicate name
    if any(m['name'].lower() == name.lower() for m in room['members']):
        return emit('sw_error', {'msg': 'Name already taken in this room'})
    room['members'].append({'sid': sid, 'name': name, 'data': None})
    sid_to_room[sid] = code
    sio_join(code)
    emit('sw_joined', {'code': code, 'name': name})
    # Notify room of member list update
    names = [m['name'] for m in room['members']]
    submitted = [m['name'] for m in room['members'] if m['data'] is not None]
    emit('sw_members_update', {'members': names, 'submitted': submitted}, to=code)


@socketio.on('sw_submit_data')
def on_sw_submit(data):
    sid = request.sid
    code = sid_to_room.get(sid)
    if not code or code not in rooms:
        return emit('sw_error', {'msg': 'Not in a room'})
    room = rooms[code]
    member = next((m for m in room['members'] if m['sid'] == sid), None)
    if not member:
        return
    personal_cost = data.get('personal_cost', 0)
    amount_paid = data.get('amount_paid', 0)
    member['data'] = {'personal_cost': personal_cost, 'amount_paid': amount_paid}
    emit('sw_submitted', {'name': member['name']})
    # Broadcast updated submitted list
    names = [m['name'] for m in room['members']]
    submitted = [m['name'] for m in room['members'] if m['data'] is not None]
    emit('sw_members_update', {'members': names, 'submitted': submitted}, to=code)


@socketio.on('sw_calculate')
def on_sw_calculate():
    sid = request.sid
    code = sid_to_room.get(sid)
    if not code or code not in rooms:
        return emit('sw_error', {'msg': 'Not in a room'})
    room = rooms[code]
    if room['host_sid'] != sid:
        return emit('sw_error', {'msg': 'Only the host can calculate'})
    # Check all submitted
    missing = [m['name'] for m in room['members'] if m['data'] is None]
    if missing:
        return emit('sw_error', {'msg': 'Waiting for: ' + ', '.join(missing)})
    people = [{'name': m['name'],
               'personal_cost': m['data']['personal_cost'],
               'amount_paid': m['data']['amount_paid']} for m in room['members']]
    total_cost = sum(p['amount_paid'] for p in people)
    result = calculate_settlements(total_cost, people)
    emit('sw_result', result, to=code)


@socketio.on('disconnect')
def on_disconnect():
    sid = request.sid
    code = sid_to_room.pop(sid, None)
    if code and code in rooms:
        room = rooms[code]
        left = next((m for m in room['members'] if m['sid'] == sid), None)
        room['members'] = [m for m in room['members'] if m['sid'] != sid]
        if not room['members']:
            del rooms[code]
        else:
            names = [m['name'] for m in room['members']]
            submitted = [m['name'] for m in room['members'] if m['data'] is not None]
            emit('sw_members_update', {'members': names, 'submitted': submitted}, to=code)
            if left:
                emit('sw_member_left', {'name': left['name']}, to=code)


if __name__ == '__main__':
    ip = socket.gethostbyname(socket.gethostname())
    print(f"\n  FunTookit is running!")
    print(f"  --> http://{ip}:5678\n")
    socketio.run(app, host='0.0.0.0', port=5678, allow_unsafe_werkzeug=True)
