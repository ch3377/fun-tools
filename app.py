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
    {
        'id': 'spy_painter',
        'name': 'Spy Painter',
        'icon': '\U0001f3a8',
        'desc': 'Draw, guess, and find the spy! Multiplayer party game.',
        'color': '#C9A0DC',
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


@app.route('/spy_painter')
def spy_painter():
    return render_template('spy_painter.html')


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
    # Aggregate entries with the same name (case-insensitive)
    merged = {}
    for p in people:
        key = p['name'].lower()
        if key in merged:
            merged[key]['personal_cost'] += p['personal_cost']
            merged[key]['amount_paid'] += p['amount_paid']
        else:
            merged[key] = dict(p)
    people = list(merged.values())

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


# ---------------------------------------------------------------------------
# Spy Painter – multiplayer draw-and-guess game
# ---------------------------------------------------------------------------
sp_rooms = {}
sp_sid_to_room = {}


def sp_get_room(sid):
    code = sp_sid_to_room.get(sid)
    if not code or code not in sp_rooms:
        return None, None
    return code, sp_rooms[code]


def sp_broadcast_players(code, room):
    players = [{'name': p['name'], 'score': p['score'],
                'is_host': p['sid'] == room['host_sid']}
               for p in room['players']]
    emit('sp_players_update', {'players': players}, to=code)


def sp_start_round(code, room):
    room['round'] += 1
    room['phase'] = 'word_suggest'
    room['suggested_words'] = []
    room['word_votes'] = {}
    room['chosen_word'] = None
    room['rejected_words'] = []
    room['drawings'] = []
    room['current_strokes'] = []
    room['spy_votes'] = {}
    # Pick spy avoiding recent repeats
    available = [i for i in range(len(room['players']))
                 if i not in room['spy_history']]
    if not available:
        room['spy_history'] = []
        available = list(range(len(room['players'])))
    room['spy_idx'] = random.choice(available)
    room['spy_history'].append(room['spy_idx'])
    for i, p in enumerate(room['players']):
        emit('sp_round_start', {
            'round': room['round'],
            'is_spy': i == room['spy_idx'],
        }, to=p['sid'])


def sp_start_drawing(code, room):
    room['phase'] = 'drawing'
    order = list(range(len(room['players'])))
    random.shuffle(order)
    room['draw_order'] = order + order
    room['current_draw_pos'] = 0
    room['current_strokes'] = []
    sp_next_drawer(code, room)


def sp_next_drawer(code, room):
    if room['current_draw_pos'] >= len(room['draw_order']):
        room['phase'] = 'spy_vote'
        room['spy_votes'] = {}
        drawings_data = []
        for d in room['drawings']:
            drawings_data.append({
                'player_name': room['players'][d['player_idx']]['name'],
                'player_idx': d['player_idx'],
                'strokes': d['strokes'],
            })
        emit('sp_gallery', {'drawings': drawings_data}, to=code)
        return
    drawer_idx = room['draw_order'][room['current_draw_pos']]
    n = len(room['players'])
    pass_num = 1 if room['current_draw_pos'] < n else 2
    room['current_strokes'] = []
    drawer_name = room['players'][drawer_idx]['name']
    for i, p in enumerate(room['players']):
        emit('sp_drawing_turn', {
            'drawer_name': drawer_name,
            'drawer_idx': drawer_idx,
            'pass_num': pass_num,
            'is_me': i == drawer_idx,
            'draw_pos': room['current_draw_pos'] + 1,
            'total_draws': len(room['draw_order']),
        }, to=p['sid'])


def sp_resolve_votes(code, room):
    room['phase'] = 'result'
    spy_idx = room['spy_idx']
    spy_name = room['players'][spy_idx]['name']
    vote_counts = {}
    vote_details = {}
    for voter_sid, target_idx in room['spy_votes'].items():
        vote_counts[target_idx] = vote_counts.get(target_idx, 0) + 1
        voter = next(p for p in room['players'] if p['sid'] == voter_sid)
        vote_details[voter['name']] = room['players'][target_idx]['name']
    max_votes = max(vote_counts.values()) if vote_counts else 0
    most_voted = [idx for idx, c in vote_counts.items() if c == max_votes]
    caught = spy_idx in most_voted and len(most_voted) == 1
    score_changes = {}
    for p in room['players']:
        score_changes[p['name']] = 0
    if caught:
        for i, p in enumerate(room['players']):
            if i != spy_idx:
                score_changes[p['name']] += 1
                p['score'] += 1
        for voter_sid, target_idx in room['spy_votes'].items():
            if target_idx == spy_idx:
                voter = next(p for p in room['players'] if p['sid'] == voter_sid)
                score_changes[voter['name']] += 2
                voter['score'] += 2
    else:
        score_changes[spy_name] = 3
        room['players'][spy_idx]['score'] += 3
    scores = [{'name': p['name'], 'score': p['score'],
               'added': score_changes[p['name']]} for p in room['players']]
    emit('sp_round_result', {
        'spy_name': spy_name,
        'spy_idx': spy_idx,
        'caught': caught,
        'chosen_word': room['chosen_word'],
        'votes': vote_details,
        'scores': scores,
    }, to=code)


@socketio.on('sp_create_room')
def on_sp_create(data):
    sid = request.sid
    name = data.get('name', '').strip()
    if not name:
        return emit('sp_error', {'msg': 'Please enter your name'})
    code = gen_code()
    while code in sp_rooms:
        code = gen_code()
    sp_rooms[code] = {
        'host_sid': sid,
        'players': [{'sid': sid, 'name': name, 'score': 0}],
        'phase': 'lobby',
        'round': 0,
        'spy_idx': None,
        'spy_history': [],
        'suggested_words': [],
        'word_votes': {},
        'chosen_word': None,
        'rejected_words': [],
        'draw_order': [],
        'current_draw_pos': 0,
        'drawings': [],
        'current_strokes': [],
        'spy_votes': {},
    }
    sp_sid_to_room[sid] = code
    sio_join(code)
    emit('sp_room_created', {'code': code, 'name': name})
    sp_broadcast_players(code, sp_rooms[code])


@socketio.on('sp_join_room')
def on_sp_join(data):
    sid = request.sid
    name = data.get('name', '').strip()
    code = data.get('code', '').strip().upper()
    if not name:
        return emit('sp_error', {'msg': 'Please enter your name'})
    if code not in sp_rooms:
        return emit('sp_error', {'msg': 'Room not found'})
    room = sp_rooms[code]
    if room['phase'] != 'lobby':
        return emit('sp_error', {'msg': 'Game already in progress'})
    if any(p['name'].lower() == name.lower() for p in room['players']):
        return emit('sp_error', {'msg': 'Name already taken'})
    if len(room['players']) >= 8:
        return emit('sp_error', {'msg': 'Room is full (max 8)'})
    room['players'].append({'sid': sid, 'name': name, 'score': 0})
    sp_sid_to_room[sid] = code
    sio_join(code)
    emit('sp_joined', {'code': code, 'name': name})
    sp_broadcast_players(code, room)


@socketio.on('sp_start_game')
def on_sp_start():
    sid = request.sid
    code, room = sp_get_room(sid)
    if not room:
        return
    if room['host_sid'] != sid:
        return emit('sp_error', {'msg': 'Only host can start'})
    if len(room['players']) < 3:
        return emit('sp_error', {'msg': 'Need at least 3 players'})
    sp_start_round(code, room)


@socketio.on('sp_suggest_word')
def on_sp_suggest(data):
    sid = request.sid
    code, room = sp_get_room(sid)
    if not room or room['phase'] != 'word_suggest':
        return
    player_idx = next((i for i, p in enumerate(room['players'])
                       if p['sid'] == sid), None)
    if player_idx is None or player_idx == room['spy_idx']:
        return
    if any(w['sid'] == sid for w in room['suggested_words']):
        return emit('sp_error', {'msg': 'You already suggested a word'})
    word = data.get('word', '').strip()
    if not word:
        return emit('sp_error', {'msg': 'Enter a word'})
    room['suggested_words'].append({'word': word, 'sid': sid})
    words = [w['word'] for w in room['suggested_words']]
    for i, p in enumerate(room['players']):
        if i != room['spy_idx']:
            emit('sp_words_update', {'words': words}, to=p['sid'])
    non_spy_count = len(room['players']) - 1
    if len(room['suggested_words']) >= non_spy_count:
        room['phase'] = 'word_vote'
        for i, p in enumerate(room['players']):
            if i != room['spy_idx']:
                emit('sp_vote_phase', {'words': words}, to=p['sid'])


@socketio.on('sp_vote_word')
def on_sp_vote(data):
    sid = request.sid
    code, room = sp_get_room(sid)
    if not room or room['phase'] != 'word_vote':
        return
    player_idx = next((i for i, p in enumerate(room['players'])
                       if p['sid'] == sid), None)
    if player_idx is None or player_idx == room['spy_idx']:
        return
    word_idx = data.get('word_idx')
    if word_idx is None or word_idx < 0 or word_idx >= len(room['suggested_words']):
        return
    room['word_votes'][sid] = word_idx
    non_spy_count = len(room['players']) - 1
    if len(room['word_votes']) >= non_spy_count:
        vote_counts = {}
        for v in room['word_votes'].values():
            vote_counts[v] = vote_counts.get(v, 0) + 1
        max_v = max(vote_counts.values())
        winners = [i for i, c in vote_counts.items() if c == max_v]
        winner_idx = random.choice(winners)
        room['chosen_word'] = room['suggested_words'][winner_idx]['word']
        room['rejected_words'] = [w['word'] for i, w in
                                   enumerate(room['suggested_words'])
                                   if i != winner_idx]
        for i, p in enumerate(room['players']):
            if i == room['spy_idx']:
                emit('sp_word_result', {
                    'is_spy': True,
                    'rejected_words': room['rejected_words'],
                }, to=p['sid'])
            else:
                emit('sp_word_result', {
                    'is_spy': False,
                    'chosen_word': room['chosen_word'],
                }, to=p['sid'])
        sp_start_drawing(code, room)


@socketio.on('sp_stroke')
def on_sp_stroke(data):
    sid = request.sid
    code, room = sp_get_room(sid)
    if not room or room['phase'] != 'drawing':
        return
    drawer_idx = room['draw_order'][room['current_draw_pos']]
    if room['players'][drawer_idx]['sid'] != sid:
        return
    stroke = data.get('stroke')
    if not stroke:
        return
    room['current_strokes'].append(stroke)
    emit('sp_stroke_broadcast', {'stroke': stroke}, to=code,
         include_self=False)


@socketio.on('sp_undo')
def on_sp_undo():
    sid = request.sid
    code, room = sp_get_room(sid)
    if not room or room['phase'] != 'drawing':
        return
    drawer_idx = room['draw_order'][room['current_draw_pos']]
    if room['players'][drawer_idx]['sid'] != sid:
        return
    if room['current_strokes']:
        room['current_strokes'].pop()
    emit('sp_undo_broadcast', {}, to=code, include_self=False)


@socketio.on('sp_clear_canvas')
def on_sp_clear():
    sid = request.sid
    code, room = sp_get_room(sid)
    if not room or room['phase'] != 'drawing':
        return
    drawer_idx = room['draw_order'][room['current_draw_pos']]
    if room['players'][drawer_idx]['sid'] != sid:
        return
    room['current_strokes'] = []
    emit('sp_clear_broadcast', {}, to=code, include_self=False)


@socketio.on('sp_draw_done')
def on_sp_draw_done():
    sid = request.sid
    code, room = sp_get_room(sid)
    if not room or room['phase'] != 'drawing':
        return
    drawer_idx = room['draw_order'][room['current_draw_pos']]
    if room['players'][drawer_idx]['sid'] != sid:
        return
    completed_strokes = list(room['current_strokes'])
    room['drawings'].append({
        'player_idx': drawer_idx,
        'strokes': completed_strokes,
    })
    # Broadcast completed drawing to everyone immediately
    emit('sp_drawing_complete', {
        'player_name': room['players'][drawer_idx]['name'],
        'player_idx': drawer_idx,
        'strokes': completed_strokes,
    }, to=code)
    room['current_draw_pos'] += 1
    sp_next_drawer(code, room)


@socketio.on('sp_vote_spy')
def on_sp_vote_spy(data):
    sid = request.sid
    code, room = sp_get_room(sid)
    if not room or room['phase'] != 'spy_vote':
        return
    player_idx = next((i for i, p in enumerate(room['players'])
                       if p['sid'] == sid), None)
    if player_idx is None:
        return
    target_idx = data.get('target_idx')
    if target_idx is None or target_idx < 0 or target_idx >= len(room['players']):
        return
    if target_idx == player_idx:
        return emit('sp_error', {'msg': "Can't vote for yourself"})
    room['spy_votes'][sid] = target_idx
    emit('sp_vote_count', {
        'count': len(room['spy_votes']),
        'total': len(room['players']),
    }, to=code)
    if len(room['spy_votes']) >= len(room['players']):
        sp_resolve_votes(code, room)


@socketio.on('sp_next_round')
def on_sp_next_round():
    sid = request.sid
    code, room = sp_get_room(sid)
    if not room or room['phase'] != 'result':
        return
    if room['host_sid'] != sid:
        return emit('sp_error', {'msg': 'Only host can start next round'})
    sp_start_round(code, room)


# ---------------------------------------------------------------------------
# Disconnect handling (Splitwiser + Spy Painter)
# ---------------------------------------------------------------------------
@socketio.on('disconnect')
def on_disconnect():
    sid = request.sid
    # Splitwiser cleanup
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
    # Spy Painter cleanup
    sp_code = sp_sid_to_room.pop(sid, None)
    if sp_code and sp_code in sp_rooms:
        sp_room = sp_rooms[sp_code]
        left = next((p for p in sp_room['players'] if p['sid'] == sid), None)
        sp_room['players'] = [p for p in sp_room['players'] if p['sid'] != sid]
        if not sp_room['players']:
            del sp_rooms[sp_code]
        else:
            if left:
                emit('sp_player_left', {'name': left['name']}, to=sp_code)
            if sp_room['phase'] != 'lobby':
                sp_room['phase'] = 'lobby'
                sp_room['round'] = 0
                sp_room['spy_history'] = []
                emit('sp_game_ended', {
                    'reason': left['name'] + ' disconnected'
                }, to=sp_code)
            sp_broadcast_players(sp_code, sp_room)


if __name__ == '__main__':
    ip = socket.gethostbyname(socket.gethostname())
    print(f"\n  FunTookit is running!")
    print(f"  --> http://{ip}:5678\n")
    socketio.run(app, host='0.0.0.0', port=5678, allow_unsafe_werkzeug=True)
