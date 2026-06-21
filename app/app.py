import os
import hashlib
import functools
import uuid
import json
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, g
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.secret_key = 'ddgl_2026_secret_key_fixed_do_not_change'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(os.path.dirname(__file__), '..', 'data.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

db = SQLAlchemy(app)

ROLE_CHOICES = [
    ('system_admin', '系统管理员'),
    ('company_admin', '公司管理员'),
    ('dispatcher', '派单员'),
    ('player', '打手'),
    ('customer_service', '客服'),
    ('finance', '财务'),
]

ORDER_STATES = {
    0: '待完善', 1: '待分配', 2: '待抢单', 3: '待上号',
    4: '代练中', 5: '待验收', 6: '已完成', 10: '已暂停',
    11: '异常中', 12: '问题单', 13: '已退单', 21: '撤销中',
    22: '仲裁中', 23: '已撤销', 24: '已仲裁',
}

ORDER_TYPES = {0: '代练订单', 1: '陪玩订单'}

PERMISSION_TREE = [
    {'id': 'dashboard', 'title': '控制台', 'children': []},
    {'id': 'general', 'title': '常规管理', 'children': [
        {'id': 'general_profile', 'title': '个人资料', 'children': []},
    ]},
    {'id': 'auth', 'title': '权限管理', 'children': [
        {'id': 'auth_role', 'title': '角色管理', 'children': []},
        {'id': 'auth_admin', 'title': '用户管理', 'children': []},
        {'id': 'auth_adminlog', 'title': '管理员日志', 'children': []},
    ]},
    {'id': 'company', 'title': '公司管理', 'children': [
        {'id': 'company_role', 'title': '公司角色管理', 'children': []},
        {'id': 'company_user', 'title': '公司用户管理', 'children': []},
        {'id': 'company_source', 'title': '来源管理', 'children': []},
    ]},
    {'id': 'game', 'title': '游戏管理', 'children': [
        {'id': 'game_manage', 'title': '游戏与区服', 'children': []},
    ]},
    {'id': 'order', 'title': '订单管理', 'children': [
        {'id': 'order_paidan', 'title': '指派给我的订单', 'children': []},
        {'id': 'order_qiangdan', 'title': '内部抢单池', 'children': []},
        {'id': 'order_all', 'title': '全部订单', 'children': []},
        {'id': 'order_add', 'title': '录单', 'children': []},
    ]},
    {'id': 'finance', 'title': '财务相关', 'children': [
        {'id': 'finance_bill', 'title': '收益管理', 'children': []},
    ]},
]


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(128), nullable=False)
    nickname = db.Column(db.String(80), default='')
    avatar = db.Column(db.String(255), default='/static/img/avatar.png')
    role_id = db.Column(db.Integer, db.ForeignKey('role.id'), nullable=True)
    is_agent = db.Column(db.Boolean, default=False)
    agent_level = db.Column(db.Integer, default=0)
    parent_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    status = db.Column(db.String(20), default='normal')
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    last_login = db.Column(db.DateTime, nullable=True)

    role = db.relationship('Role', backref='users')
    parent = db.relationship('User', remote_side=[id], backref='children')

    def check_password(self, pwd):
        return self.password == hashlib.md5(pwd.encode()).hexdigest()

    def set_password(self, pwd):
        self.password = hashlib.md5(pwd.encode()).hexdigest()

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'nickname': self.nickname or self.username,
            'avatar': self.avatar,
            'role_id': self.role_id,
            'role_name': self.role.name if self.role else '',
            'is_agent': self.is_agent,
            'agent_level': self.agent_level,
            'parent_id': self.parent_id,
            'status': self.status,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else '',
            'last_login': self.last_login.strftime('%Y-%m-%d %H:%M:%S') if self.last_login else '',
        }


class LoginToken(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(128), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    expires_at = db.Column(db.DateTime)

    user = db.relationship('User', backref='login_tokens')


class Role(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    desc = db.Column(db.String(255), default='')
    permissions = db.Column(db.Text, default='[]')
    created_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):

        return {
            'id': self.id,
            'name': self.name,
            'desc': self.desc,
            'permissions': json.loads(self.permissions) if self.permissions else [],
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else '',
        }


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_no = db.Column(db.String(64), unique=True, nullable=False)
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'), nullable=True)
    area_id = db.Column(db.Integer, db.ForeignKey('game_area.id'), nullable=True)
    server_id = db.Column(db.Integer, db.ForeignKey('game_server.id'), nullable=True)
    order_type = db.Column(db.Integer, default=0)
    state = db.Column(db.Integer, default=0)
    title = db.Column(db.String(255), default='')
    description = db.Column(db.Text, default='')
    amount = db.Column(db.Float, default=0)
    cost = db.Column(db.Float, default=0)
    source_id = db.Column(db.Integer, db.ForeignKey('source.id'), nullable=True)
    creator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    is_priority = db.Column(db.Boolean, default=False)
    character_name = db.Column(db.String(100), default='')
    account_info = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    finished_at = db.Column(db.DateTime, nullable=True)

    game = db.relationship('Game', backref='orders')
    area = db.relationship('GameArea', backref='orders')
    server = db.relationship('GameServer', backref='orders')
    source = db.relationship('Source', backref='orders')
    creator = db.relationship('User', foreign_keys=[creator_id], backref='created_orders')
    receiver = db.relationship('User', foreign_keys=[receiver_id], backref='received_orders')

    def to_dict(self):
        return {
            'id': self.id,
            'order_no': self.order_no,
            'game_id': self.game_id,
            'game_name': self.game.name if self.game else '',
            'area_id': self.area_id,
            'game_area': self.area.name if self.area else '',
            'server_id': self.server_id,
            'game_server': self.server.name if self.server else '',
            'order_type': self.order_type,
            'order_type_name': ORDER_TYPES.get(self.order_type, '未知'),
            'state': self.state,
            'state_name': ORDER_STATES.get(self.state, '未知'),
            'title': self.title,
            'description': self.description,
            'amount': self.amount,
            'cost': self.cost,
            'source_name': self.source.name if self.source else '',
            'creator_name': self.creator.nickname or self.creator.username if self.creator else '',
            'receiver_name': self.receiver.nickname or self.receiver.username if self.receiver else '',
            'is_priority': self.is_priority,
            'character_name': self.character_name,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else '',
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S') if self.updated_at else '',
            'finished_at': self.finished_at.strftime('%Y-%m-%d %H:%M:%S') if self.finished_at else '',
        }


class Source(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    desc = db.Column(db.String(255), default='')
    created_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'desc': self.desc,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else '',
        }


class Game(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    icon = db.Column(db.String(255), default='')
    sort = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default='normal')
    created_at = db.Column(db.DateTime, default=datetime.now)

    areas = db.relationship('GameArea', backref='game', cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'icon': self.icon,
            'sort': self.sort,
            'status': self.status,
            'area_count': len(self.areas),
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else '',
        }


class GameArea(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    sort = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.now)

    servers = db.relationship('GameServer', backref='area', cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'game_id': self.game_id,
            'name': self.name,
            'sort': self.sort,
            'server_count': len(self.servers),
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else '',
        }


class GameServer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    area_id = db.Column(db.Integer, db.ForeignKey('game_area.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    sort = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {
            'id': self.id,
            'area_id': self.area_id,
            'name': self.name,
            'sort': self.sort,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else '',
        }


class AdminLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    action = db.Column(db.String(255), default='')
    url = db.Column(db.String(255), default='')
    ip = db.Column(db.String(50), default='')
    created_at = db.Column(db.DateTime, default=datetime.now)

    user = db.relationship('User', backref='logs')

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'username': self.user.nickname or self.user.username if self.user else '',
            'action': self.action,
            'url': self.url,
            'ip': self.ip,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else '',
        }


class Bill(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    bill_type = db.Column(db.String(20), default='player')
    amount = db.Column(db.Float, default=0)
    state = db.Column(db.String(20), default='unpaid')
    created_at = db.Column(db.DateTime, default=datetime.now)
    settled_at = db.Column(db.DateTime, nullable=True)

    order = db.relationship('Order', backref='bills')
    user = db.relationship('User', backref='bills')

    def to_dict(self):
        order = self.order
        if order:
            order_dict = order.to_dict()
        else:
            order_dict = {}
        return {
            'id': self.id,
            'order_id': self.order_id,
            'order_no': order_dict.get('order_no', ''),
            'game_name': order_dict.get('game_name', ''),
            'game_area': order_dict.get('game_area', ''),
            'title': order_dict.get('title', ''),
            'order_amount': order_dict.get('amount', 0),
            'order_cost': order_dict.get('cost', 0),
            'order_type_name': order_dict.get('order_type_name', ''),
            'character_name': order_dict.get('character_name', ''),
            'source_name': order_dict.get('source_name', ''),
            'creator_name': order_dict.get('creator_name', ''),
            'receiver_name': order_dict.get('receiver_name', ''),
            'user_id': self.user_id,
            'username': (self.user.nickname or self.user.username) if self.user else '',
            'bill_type': self.bill_type,
            'bill_type_name': '打手报酬' if self.bill_type == 'player' else '客服报酬',
            'amount': self.amount,
            'state': self.state,
            'state_name': {'unpaid': '未结算', 'settling': '结算中', 'settled': '已结算'}.get(self.state, '未知'),
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else '',
            'settled_at': self.settled_at.strftime('%Y-%m-%d %H:%M:%S') if self.settled_at else '',
        }


def is_normal_user(user):
    if not user or not user.role:
        return True
    return 'system_admin' not in (json.loads(user.role.permissions) if user.role.permissions else [])


def get_current_user():
    token = request.args.get('token') or request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return None
    lt = LoginToken.query.filter_by(token=token).first()
    if not lt:
        return None
    if lt.expires_at and lt.expires_at < datetime.now():
        db.session.delete(lt)
        db.session.commit()
        return None
    user = User.query.get(lt.user_id)
    if not user or user.status != 'normal':
        return None
    return user


def login_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            if request.is_json or request.headers.get('Accept', '').startswith('application/json') or request.args.get('token'):
                return jsonify({'code': 0, 'msg': '请登录后操作'}), 401
            return redirect(url_for('login'))
        g.user = user
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({'code': 0, 'msg': '请登录后操作'}), 401
        if user.status != 'normal':
            return jsonify({'code': 0, 'msg': '账号已被禁用，请联系管理员'}), 401
        if not user.role or 'system_admin' not in (json.loads(user.role.permissions) if user.role.permissions else []):
            return jsonify({'code': 0, 'msg': '你没有管理员权限，请重新登录'}), 403
        g.user = user
        return f(*args, **kwargs)
    return decorated


def perm_required(perm_id):
    def decorator(f):
        @functools.wraps(f)
        def decorated(*args, **kwargs):
            user = get_current_user()
            if not user:
                return jsonify({'code': 0, 'msg': '请登录后操作'}), 401
            if not user.role:
                return jsonify({'code': 0, 'msg': '你没有权限访问'}), 403
            perms = json.loads(user.role.permissions) if user.role.permissions else []
            if 'system_admin' in perms or perm_id in perms:
                g.user = user
                return f(*args, **kwargs)
            return jsonify({'code': 0, 'msg': '你没有权限访问'}), 403
        return decorated
    return decorator


def add_log(action, url=''):
    user = getattr(g, 'user', None)
    if user:
        log = AdminLog(user_id=user.id, action=action, url=url, ip=request.remote_addr)
        db.session.add(log)
        db.session.commit()


def cascade_freeze(parent_id):
    children = User.query.filter_by(parent_id=parent_id).all()
    for child in children:
        child.status = 'hidden'
        if child.is_agent:
            cascade_freeze(child.id)


def cascade_delete(parent_id):
    children = User.query.filter_by(parent_id=parent_id).all()
    for child in children:
        if child.is_agent:
            cascade_delete(child.id)
        db.session.delete(child)


def get_user_tree_ids(uid):
    ids = [uid]
    children = User.query.filter_by(parent_id=uid).all()
    for child in children:
        ids.extend(get_user_tree_ids(child.id))
    return ids


def gen_order_no():
    return datetime.now().strftime('%Y%m%d%H%M%S') + str(uuid.uuid4().int)[:4]


# ============ 页面路由 ============

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')
    data = request.get_json() or request.form
    username = data.get('username', '')
    password = data.get('password', '')
    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(password):
        return jsonify({'code': 0, 'msg': '用户名或密码错误'})
    if user.status != 'normal':
        return jsonify({'code': 0, 'msg': '账号已被禁用'})
    token_str = uuid.uuid4().hex + uuid.uuid4().hex
    lt = LoginToken(token=token_str, user_id=user.id, expires_at=datetime.now() + timedelta(days=7))
    db.session.add(lt)
    user.last_login = datetime.now()
    db.session.commit()
    return jsonify({'code': 1, 'msg': '登录成功', 'token': token_str})


@app.route('/api/current_user', methods=['GET'])
def api_current_user():
    user = get_current_user()
    if not user:
        return jsonify({'code': 0, 'msg': '未登录'}), 401
    perms = json.loads(user.role.permissions) if user.role and user.role.permissions else []
    return jsonify({
        'code': 1,
        'data': {
            'id': user.id,
            'username': user.username,
            'nickname': user.nickname or user.username,
            'avatar': user.avatar,
            'is_agent': user.is_agent,
            'role_name': user.role.name if user.role else '未分配',
            'last_login': user.last_login.strftime('%Y-%m-%d %H:%M:%S') if user.last_login else '',
            'permissions': perms,
            'permission_tree': PERMISSION_TREE,
        }
    })


@app.route('/logout')
def logout():
    return redirect(url_for('login'))


@app.route('/companymaintain/rolemanage')
@login_required
def role_manage():
    return render_template('role_manage.html')


@app.route('/companymaintain/adminmanage')
@login_required
def admin_manage():
    return render_template('admin_manage.html')


@app.route('/companymaintain/sourcemanage')
@login_required
def source_manage():
    return render_template('source_manage.html')


@app.route('/gamemanage/index')
@login_required
def game_manage():
    return render_template('game_manage.html')


@app.route('/companypaidan/index')
@login_required
def paidan_index():
    return render_template('paidan.html')


@app.route('/companyqiangdan/index')
@login_required
def qiangdan_index():
    return render_template('qiangdan.html')


@app.route('/companyorder/index')
@login_required
def order_index():
    return render_template('order_all.html')


@app.route('/companyorder/add')
@login_required
def order_add():
    return render_template('order_add.html')


@app.route('/Companyobill/userlist')
@login_required
def bill_userlist():
    return render_template('bill.html')


@app.route('/general/profile')
@login_required
def profile():
    return render_template('profile.html')


@app.route('/auth/adminlog')
@login_required
def admin_log():
    return render_template('admin_log.html')


# ============ API路由 ============

@app.route('/api/roles', methods=['GET'])
@login_required
def api_roles():
    roles = Role.query.all()
    user = g.user
    is_admin = user.role and 'system_admin' in (json.loads(user.role.permissions) if user.role.permissions else [])
    if not is_admin:
        restricted = ['system_admin', 'company_admin']
        filtered = []
        for r in roles:
            rperms = json.loads(r.permissions) if r.permissions else []
            if any(p in rperms for p in restricted):
                continue
            if r.name == '代理':
                continue
            filtered.append(r)
        roles = filtered
    return jsonify({'code': 0, 'data': [r.to_dict() for r in roles], 'count': len(roles)})


@app.route('/api/roles', methods=['POST'])
@admin_required
def api_role_add():
    data = request.get_json()
    import json
    role = Role(name=data.get('name', ''), desc=data.get('desc', ''), permissions=json.dumps(data.get('permissions', [])))
    db.session.add(role)
    db.session.commit()
    add_log(f'新增角色: {role.name}', '/api/roles')
    return jsonify({'code': 1, 'msg': '添加成功'})


@app.route('/api/roles/<int:rid>', methods=['PUT'])
@admin_required
def api_role_edit(rid):
    role = Role.query.get_or_404(rid)
    data = request.get_json()
    import json
    role.name = data.get('name', role.name)
    role.desc = data.get('desc', role.desc)
    role.permissions = json.dumps(data.get('permissions', json.loads(role.permissions)))
    db.session.commit()
    add_log(f'修改角色: {role.name}', f'/api/roles/{rid}')
    return jsonify({'code': 1, 'msg': '修改成功'})


@app.route('/api/roles/<int:rid>', methods=['DELETE'])
@admin_required
def api_role_del(rid):
    role = Role.query.get_or_404(rid)
    if role.users:
        return jsonify({'code': 0, 'msg': '该角色下有用户，无法删除'})
    db.session.delete(role)
    db.session.commit()
    add_log(f'删除角色: {role.name}', f'/api/roles/{rid}')
    return jsonify({'code': 1, 'msg': '删除成功'})


@app.route('/api/permission_tree', methods=['GET'])
@login_required
def api_permission_tree():
    return jsonify({'code': 0, 'data': PERMISSION_TREE})


@app.route('/api/users', methods=['GET'])
@login_required
def api_users():
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 10, type=int)
    keyword = request.args.get('keyword', '')
    q = User.query

    current_user = g.user
    if is_normal_user(current_user):
        tree_ids = get_user_tree_ids(current_user.id)
        q = q.filter(User.id.in_(tree_ids))

    if keyword:
        q = q.filter((User.username.contains(keyword)) | (User.nickname.contains(keyword)))
    total = q.count()
    users = q.offset((page - 1) * limit).limit(limit).all()
    return jsonify({'code': 0, 'data': [u.to_dict() for u in users], 'count': total})


@app.route('/api/users', methods=['POST'])
@admin_required
def api_user_add():
    data = request.get_json()
    username = data.get('username', '').strip()
    if not username:
        return jsonify({'code': 0, 'msg': '用户名不能为空'})
    if User.query.filter_by(username=username).first():
        return jsonify({'code': 0, 'msg': '用户名已存在'})
    user = User(username=username)
    pwd = data.get('password', '')
    user.set_password(pwd if pwd else '123456')
    user.nickname = data.get('nickname', '')
    user.role_id = data.get('role_id')
    user.is_agent = data.get('is_agent', False)
    user.agent_level = data.get('agent_level', 0)
    user.parent_id = data.get('parent_id')
    user.status = data.get('status', 'normal')
    db.session.add(user)
    db.session.commit()
    add_log(f'新增用户: {user.username}', '/api/users')
    return jsonify({'code': 1, 'msg': '添加成功'})


@app.route('/api/users/<int:uid>', methods=['PUT'])
@admin_required
def api_user_edit(uid):
    user = User.query.get_or_404(uid)
    data = request.get_json()
    if 'nickname' in data:
        user.nickname = data['nickname']
    if 'role_id' in data:
        user.role_id = data['role_id']
    if 'is_agent' in data:
        user.is_agent = data['is_agent']
    if 'agent_level' in data:
        user.agent_level = data['agent_level']
    if 'parent_id' in data:
        user.parent_id = data['parent_id']
    if 'status' in data:
        old_status = user.status
        user.status = data['status']
        if data['status'] == 'hidden' and old_status == 'normal' and user.is_agent:
            cascade_freeze(uid)
    if 'password' in data and data['password']:
        user.set_password(data['password'])
    if 'parent_id' in data:
        new_pid = data['parent_id']
        if new_pid == uid:
            return jsonify({'code': 0, 'msg': '不能设置自己为上级'})
        user.parent_id = new_pid
    db.session.commit()
    add_log(f'修改用户: {user.username}', f'/api/users/{uid}')
    return jsonify({'code': 1, 'msg': '修改成功'})


@app.route('/api/users/<int:uid>', methods=['DELETE'])
@admin_required
def api_user_del(uid):
    user = User.query.get_or_404(uid)
    cascade_delete(uid)
    db.session.delete(user)
    db.session.commit()
    add_log(f'删除用户: {user.username}', f'/api/users/{uid}')
    return jsonify({'code': 1, 'msg': '删除成功'})


@app.route('/api/users/<int:uid>/set_agent', methods=['POST'])
@admin_required
def api_user_set_agent(uid):
    user = User.query.get_or_404(uid)
    data = request.get_json()
    user.is_agent = data.get('is_agent', not user.is_agent)
    user.agent_level = data.get('agent_level', user.agent_level)
    if 'parent_id' in data:
        user.parent_id = data['parent_id']
    db.session.commit()
    add_log(f'设置代理: {user.username}', f'/api/users/{uid}/set_agent')
    return jsonify({'code': 1, 'msg': '设置成功'})


@app.route('/api/sources', methods=['GET'])
@login_required
def api_sources():
    sources = Source.query.all()
    return jsonify({'code': 0, 'data': [s.to_dict() for s in sources], 'count': len(sources)})


@app.route('/api/sources', methods=['POST'])
@login_required
def api_source_add():
    data = request.get_json()
    source = Source(name=data.get('name', ''), desc=data.get('desc', ''))
    db.session.add(source)
    db.session.commit()
    add_log(f'新增来源: {source.name}', '/api/sources')
    return jsonify({'code': 1, 'msg': '添加成功'})


@app.route('/api/sources/<int:sid>', methods=['PUT'])
@login_required
def api_source_edit(sid):
    source = Source.query.get_or_404(sid)
    data = request.get_json()
    source.name = data.get('name', source.name)
    source.desc = data.get('desc', source.desc)
    db.session.commit()
    return jsonify({'code': 1, 'msg': '修改成功'})


@app.route('/api/sources/<int:sid>', methods=['DELETE'])
@login_required
def api_source_del(sid):
    source = Source.query.get_or_404(sid)
    db.session.delete(source)
    db.session.commit()
    return jsonify({'code': 1, 'msg': '删除成功'})


# ============ 游戏管理API ============

@app.route('/api/games', methods=['GET'])
@login_required
def api_games():
    games = Game.query.order_by(Game.sort, Game.id).all()
    return jsonify({'code': 0, 'data': [g.to_dict() for g in games], 'count': len(games)})


@app.route('/api/games', methods=['POST'])
@login_required
def api_game_add():
    data = request.get_json()
    game = Game(name=data.get('name', ''), icon=data.get('icon', ''), sort=data.get('sort', 0))
    db.session.add(game)
    db.session.commit()
    add_log(f'新增游戏: {game.name}', '/api/games')
    return jsonify({'code': 1, 'msg': '添加成功'})


@app.route('/api/games/<int:gid>', methods=['PUT'])
@login_required
def api_game_edit(gid):
    game = Game.query.get_or_404(gid)
    data = request.get_json()
    game.name = data.get('name', game.name)
    game.icon = data.get('icon', game.icon)
    game.sort = data.get('sort', game.sort)
    game.status = data.get('status', game.status)
    db.session.commit()
    return jsonify({'code': 1, 'msg': '修改成功'})


@app.route('/api/games/<int:gid>', methods=['DELETE'])
@login_required
def api_game_del(gid):
    game = Game.query.get_or_404(gid)
    db.session.delete(game)
    db.session.commit()
    return jsonify({'code': 1, 'msg': '删除成功'})


@app.route('/api/games/<int:gid>/areas', methods=['GET'])
@login_required
def api_game_areas(gid):
    areas = GameArea.query.filter_by(game_id=gid).order_by(GameArea.sort, GameArea.id).all()
    return jsonify({'code': 0, 'data': [a.to_dict() for a in areas], 'count': len(areas)})


@app.route('/api/games/<int:gid>/areas', methods=['POST'])
@login_required
def api_game_area_add(gid):
    data = request.get_json()
    area = GameArea(game_id=gid, name=data.get('name', ''), sort=data.get('sort', 0))
    db.session.add(area)
    db.session.commit()
    return jsonify({'code': 1, 'msg': '添加成功'})


@app.route('/api/game_areas/<int:aid>', methods=['PUT'])
@login_required
def api_game_area_edit(aid):
    area = GameArea.query.get_or_404(aid)
    data = request.get_json()
    area.name = data.get('name', area.name)
    area.sort = data.get('sort', area.sort)
    db.session.commit()
    return jsonify({'code': 1, 'msg': '修改成功'})


@app.route('/api/game_areas/<int:aid>', methods=['DELETE'])
@login_required
def api_game_area_del(aid):
    area = GameArea.query.get_or_404(aid)
    db.session.delete(area)
    db.session.commit()
    return jsonify({'code': 1, 'msg': '删除成功'})


@app.route('/api/game_areas/<int:aid>/servers', methods=['GET'])
@login_required
def api_area_servers(aid):
    servers = GameServer.query.filter_by(area_id=aid).order_by(GameServer.sort, GameServer.id).all()
    return jsonify({'code': 0, 'data': [s.to_dict() for s in servers], 'count': len(servers)})


@app.route('/api/game_areas/<int:aid>/servers', methods=['POST'])
@login_required
def api_area_server_add(aid):
    data = request.get_json()
    srv = GameServer(area_id=aid, name=data.get('name', ''), sort=data.get('sort', 0))
    db.session.add(srv)
    db.session.commit()
    return jsonify({'code': 1, 'msg': '添加成功'})


@app.route('/api/game_servers/<int:sid>', methods=['PUT'])
@login_required
def api_game_server_edit(sid):
    srv = GameServer.query.get_or_404(sid)
    data = request.get_json()
    srv.name = data.get('name', srv.name)
    srv.sort = data.get('sort', srv.sort)
    db.session.commit()
    return jsonify({'code': 1, 'msg': '修改成功'})


@app.route('/api/game_servers/<int:sid>', methods=['DELETE'])
@login_required
def api_game_server_del(sid):
    srv = GameServer.query.get_or_404(sid)
    db.session.delete(srv)
    db.session.commit()
    return jsonify({'code': 1, 'msg': '删除成功'})


@app.route('/api/orders', methods=['GET'])
@login_required
def api_orders():
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 10, type=int)
    state = request.args.get('state', '')
    keyword = request.args.get('keyword', '')
    game_id = request.args.get('game_id', '')
    order_type = request.args.get('order_type', '')
    view = request.args.get('view', 'all')
    q = Order.query

    current_user = g.user
    if is_normal_user(current_user):
        tree_ids = get_user_tree_ids(current_user.id)
        q = q.filter(db.or_(Order.creator_id.in_(tree_ids), Order.receiver_id.in_(tree_ids)))

    if state != '':
        q = q.filter_by(state=int(state))
    if keyword:
        q = q.filter((Order.order_no.contains(keyword)) | (Order.character_name.contains(keyword)))
    if game_id:
        q = q.filter_by(game_id=int(game_id))
    if order_type != '':
        q = q.filter_by(order_type=int(order_type))
    if view == 'paidan':
        q = q.filter(Order.receiver_id == current_user.id, Order.state.in_([3, 4, 5]))
    elif view == 'qiangdan':
        q = q.filter_by(state=2)
    total = q.count()
    orders = q.order_by(Order.created_at.desc()).offset((page - 1) * limit).limit(limit).all()
    return jsonify({'code': 0, 'data': [o.to_dict() for o in orders], 'count': total})


@app.route('/api/orders', methods=['POST'])
@login_required
def api_order_add():
    data = request.get_json()
    order = Order(
        order_no=gen_order_no(),
        game_id=data.get('game_id'),
        area_id=data.get('area_id'),
        server_id=data.get('server_id'),
        order_type=data.get('order_type', 0),
        state=data.get('state', 1),
        title=data.get('title', ''),
        description=data.get('description', ''),
        amount=data.get('amount', 0),
        cost=data.get('cost', 0),
        source_id=data.get('source_id'),
        creator_id=g.user.id,
        is_priority=data.get('is_priority', False),
        character_name=data.get('character_name', ''),
        account_info=data.get('account_info', ''),
    )
    db.session.add(order)
    db.session.commit()
    add_log(f'录单: {order.order_no}', '/api/orders')
    return jsonify({'code': 1, 'msg': '录单成功', 'data': order.to_dict()})


@app.route('/api/orders/<int:oid>', methods=['PUT'])
@login_required
def api_order_edit(oid):
    order = Order.query.get_or_404(oid)
    data = request.get_json()
    for k in ['order_type', 'title', 'description',
              'amount', 'cost', 'source_id', 'is_priority', 'character_name', 'account_info',
              'game_id', 'area_id', 'server_id']:
        if k in data:
            setattr(order, k, data[k])
    if 'state' in data:
        new_state = int(data['state'])
        order.state = new_state
        if new_state == 6:
            order.finished_at = datetime.now()
            if order.receiver_id and not Bill.query.filter_by(order_id=order.id, user_id=order.receiver_id).first():
                bill = Bill(order_id=order.id, user_id=order.receiver_id, bill_type='player', amount=order.cost or 0, state='unpaid')
                db.session.add(bill)
            if order.creator_id and order.creator_id != order.receiver_id and not Bill.query.filter_by(order_id=order.id, user_id=order.creator_id).first():
                bill2 = Bill(order_id=order.id, user_id=order.creator_id, bill_type='service', amount=(order.amount or 0) - (order.cost or 0), state='unpaid')
                db.session.add(bill2)
    if 'receiver_id' in data:
        order.receiver_id = data['receiver_id']
        if order.state == 1:
            order.state = 3
    db.session.commit()
    add_log(f'修改订单: {order.order_no}', f'/api/orders/{oid}')
    return jsonify({'code': 1, 'msg': '修改成功'})


@app.route('/api/orders/<int:oid>/receive', methods=['POST'])
@login_required
def api_order_receive(oid):
    order = Order.query.get_or_404(oid)
    if order.state != 2:
        return jsonify({'code': 0, 'msg': '该订单不在待抢单状态'})
    order.receiver_id = g.user.id
    order.state = 3
    db.session.commit()
    add_log(f'接手订单: {order.order_no}', f'/api/orders/{oid}/receive')
    return jsonify({'code': 1, 'msg': '接手成功'})


@app.route('/api/orders/<int:oid>/finish', methods=['POST'])
@login_required
def api_order_finish(oid):
    order = Order.query.get_or_404(oid)
    if order.state != 4:
        return jsonify({'code': 0, 'msg': '该订单不在代练中状态'})
    order.state = 5
    db.session.commit()
    add_log(f'提交验收: {order.order_no}', f'/api/orders/{oid}/finish')
    return jsonify({'code': 1, 'msg': '提交验收成功'})


@app.route('/api/bills', methods=['GET'])
@login_required
def api_bills():
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 10, type=int)
    bill_type = request.args.get('bill_type', '')
    state = request.args.get('state', '')
    keyword = request.args.get('keyword', '')
    q = Bill.query

    current_user = g.user
    if is_normal_user(current_user):
        tree_ids = get_user_tree_ids(current_user.id)
        q = q.filter(Bill.user_id.in_(tree_ids))

    if bill_type:
        q = q.filter_by(bill_type=bill_type)
    if state:
        q = q.filter_by(state=state)
    if keyword:
        q = q.join(Bill.order, isouter=True).filter(db.or_(Order.order_no.contains(keyword), Order.character_name.contains(keyword)))
    total = q.count()
    bills = q.order_by(Bill.created_at.desc()).offset((page - 1) * limit).limit(limit).all()
    return jsonify({'code': 0, 'data': [b.to_dict() for b in bills], 'count': total})


@app.route('/api/bills/<int:bid>/settle', methods=['POST'])
@login_required
def api_bill_settle(bid):
    bill = Bill.query.get_or_404(bid)
    bill.state = 'settled'
    bill.settled_at = datetime.now()
    db.session.commit()
    return jsonify({'code': 1, 'msg': '结算成功'})


@app.route('/api/admin_logs', methods=['GET'])
@login_required
def api_admin_logs():
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 10, type=int)
    q = AdminLog.query
    current_user = g.user
    if is_normal_user(current_user):
        tree_ids = get_user_tree_ids(current_user.id)
        q = q.filter(AdminLog.user_id.in_(tree_ids))
    total = q.count()
    logs = q.order_by(AdminLog.created_at.desc()).offset((page - 1) * limit).limit(limit).all()
    return jsonify({'code': 0, 'data': [l.to_dict() for l in logs], 'count': total})


@app.route('/api/check_status', methods=['GET'])
@login_required
def api_check_status():
    return jsonify({'code': 1, 'msg': 'ok'})


@app.route('/api/dashboard/stats', methods=['GET'])
@login_required
def api_dashboard_stats():
    current_user = g.user
    is_agent = is_normal_user(current_user)
    if is_agent:
        tree_ids = get_user_tree_ids(current_user.id)
        oq = Order.query.filter(db.or_(Order.creator_id.in_(tree_ids), Order.receiver_id.in_(tree_ids)))
        total_orders = oq.count()
        pending = oq.filter(Order.state.in_([1, 2, 3])).count()
        doing = oq.filter_by(state=4).count()
        finished = oq.filter_by(state=6).count()
        total_users = User.query.filter(User.id.in_(tree_ids)).count()
        total_agents = User.query.filter(User.id.in_(tree_ids), User.is_agent == True).count()
    else:
        total_orders = Order.query.count()
        pending = Order.query.filter(Order.state.in_([1, 2, 3])).count()
        doing = Order.query.filter_by(state=4).count()
        finished = Order.query.filter_by(state=6).count()
        total_users = User.query.count()
        total_agents = User.query.filter_by(is_agent=True).count()
    return jsonify({
        'code': 1,
        'data': {
            'total_orders': total_orders,
            'pending': pending,
            'doing': doing,
            'finished': finished,
            'total_users': total_users,
            'total_agents': total_agents,
        }
    })


def init_db():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        admin_role = Role(name='系统管理员', desc='拥有所有权限', permissions='["system_admin"]')
        db.session.add(admin_role)
        db.session.flush()

        agent_role = Role(name='代理', desc='代理角色，可发展下级', permissions='["dashboard","general_profile","company_role","company_user","company_source","game_manage","order_paidan","order_qiangdan","order_all","order_add","finance_bill"]')
        db.session.add(agent_role)
        db.session.flush()

        player_role = Role(name='打手', desc='接单代练', permissions='["dashboard","general_profile","order_qiangdan","order_paidan"]')
        db.session.add(player_role)
        db.session.flush()

        cs_role = Role(name='客服', desc='处理客户问题', permissions='["dashboard","general_profile","order_all","order_add","order_paidan"]')
        db.session.add(cs_role)
        db.session.flush()

        finance_role = Role(name='财务', desc='财务结算', permissions='["dashboard","general_profile","finance_bill"]')
        db.session.add(finance_role)
        db.session.flush()

        admin = User(username='admin', nickname='系统管理员', role_id=admin_role.id, status='normal')
        admin.set_password('admin123')
        db.session.add(admin)

        demo_source = Source(name='淘宝店铺', desc='淘宝渠道订单')
        db.session.add(demo_source)
        demo_source2 = Source(name='拼多多店铺', desc='拼多多渠道订单')
        db.session.add(demo_source2)

        g1 = Game(name='王者荣耀', sort=1)
        g2 = Game(name='和平精英', sort=2)
        g3 = Game(name='英雄联盟', sort=3)
        g4 = Game(name='原神', sort=4)
        db.session.add_all([g1, g2, g3, g4])
        db.session.flush()

        a1 = GameArea(game_id=g1.id, name='微信区')
        a2 = GameArea(game_id=g1.id, name='QQ区')
        a3 = GameArea(game_id=g2.id, name='微信区')
        a4 = GameArea(game_id=g2.id, name='QQ区')
        a5 = GameArea(game_id=g3.id, name='电信区')
        a6 = GameArea(game_id=g3.id, name='网通区')
        a7 = GameArea(game_id=g4.id, name='官服')
        a8 = GameArea(game_id=g4.id, name='B服')
        db.session.add_all([a1, a2, a3, a4, a5, a6, a7, a8])
        db.session.flush()

        for ai in [a1, a2, a3, a4, a5, a6, a7, a8]:
            for si in range(1, 4):
                db.session.add(GameServer(area_id=ai.id, name=f'服务器{si}'))

        db.session.flush()

        orders = []
        for i in range(5):
            o = Order(
                order_no=gen_order_no(),
                game_id=[g1.id, g2.id][i % 2],
                area_id=[a1.id, a3.id][i % 2],
                server_id=[a1.servers[0].id if a1.servers else None, a3.servers[0].id if a3.servers else None][i % 2],
                order_type=i % 2,
                state=[1, 2, 3, 4, 5][i],
                title=f'代练订单{i + 1}',
                amount=50 + i * 10,
                cost=30 + i * 5,
                source_id=demo_source.id if i % 2 == 0 else demo_source2.id,
                creator_id=admin.id,
                is_priority=i == 0,
                character_name=f'角色{i + 1}',
            )
            db.session.add(o)
            orders.append(o)

        db.session.flush()

        bill_data = [
            (orders[0], admin, 'player', 15.00, 'unpaid'),
            (orders[0], admin, 'service', 5.00, 'unpaid'),
            (orders[1], admin, 'player', 20.00, 'settling'),
            (orders[1], admin, 'service', 8.00, 'settled'),
            (orders[2], admin, 'player', 25.00, 'settled'),
            (orders[2], admin, 'service', 10.00, 'settled'),
            (orders[3], admin, 'player', 30.00, 'unpaid'),
            (orders[3], admin, 'service', 12.00, 'unpaid'),
            (orders[4], admin, 'player', 35.00, 'settling'),
            (orders[4], admin, 'service', 15.00, 'settled'),
        ]
        for order, user, btype, amount, state in bill_data:
            b = Bill(order_id=order.id, user_id=user.id, bill_type=btype, amount=amount, state=state)
            if state == 'settled':
                b.settled_at = datetime.now()
            db.session.add(b)

        db.session.commit()
        print('数据库初始化完成！默认账号: admin / admin123')


if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)