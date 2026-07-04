import os
import hashlib
import functools
import uuid
import json
import threading
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, g
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'ddgl_2026_secret_key_fixed_do_not_change')
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
        {'id': 'order_ranking', 'title': '接单员月度排行', 'children': []},
        {'id': 'order_stats', 'title': '订单统计数据', 'children': []},
        {'id': 'order_logs', 'title': '订单日志', 'children': []},
    ]},
    {'id': 'finance', 'title': '财务相关', 'children': [
        {'id': 'finance_bill', 'title': '收益管理', 'children': []},
    ]},
    {'id': 'platform', 'title': '平台设置', 'children': [
        {'id': 'platform_settings', 'title': '发平台设置', 'children': []},
        {'id': 'company_info', 'title': '企业信息', 'children': []},
    ]},
    {'id': 'system', 'title': '系统管理', 'children': [
        {'id': 'system_maintain', 'title': '系统维护', 'children': []},
        {'id': 'tenant_manage', 'title': '租户管理', 'children': []},
        {'id': 'tenant_binding', 'title': '绑定上家', 'children': []},
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
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=True)
    status = db.Column(db.String(20), default='normal')
    id_card = db.Column(db.String(20), default='')
    business_type = db.Column(db.String(20), default='both')
    member_type = db.Column(db.String(20), default='internal')
    commission_mode = db.Column(db.String(20), default='fixed')
    commission_value = db.Column(db.Float, default=0)
    alipay_account = db.Column(db.String(100), default='')
    alipay_name = db.Column(db.String(50), default='')
    wechat_account = db.Column(db.String(100), default='')
    wechat_qrcode = db.Column(db.String(255), default='')
    alipay_qrcode = db.Column(db.String(255), default='')
    grab_limit_dailian = db.Column(db.Integer, default=0)
    grab_limit_peiwan = db.Column(db.Integer, default=0)
    grab_price_min = db.Column(db.Float, default=0)
    grab_price_max = db.Column(db.Float, default=99999)
    live_url = db.Column(db.String(255), default='')
    qq_wechat = db.Column(db.String(100), default='')
    phone = db.Column(db.String(30), default='')
    hire_date = db.Column(db.String(20), default='')
    mark = db.Column(db.String(100), default='')
    deposit = db.Column(db.Float, default=0)
    no_sms = db.Column(db.Boolean, default=False)
    all_games = db.Column(db.Boolean, default=False)
    game_permissions = db.Column(db.Text, default='')
    remark = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    last_login = db.Column(db.DateTime, nullable=True)

    role = db.relationship('Role', backref='users')
    parent = db.relationship('User', remote_side=[id], backref='children')
    tenant = db.relationship('Tenant', backref='users')

    def check_password(self, pwd):
        if self.password.startswith('pbkdf2:') or self.password.startswith('sha256:'):
            return check_password_hash(self.password, pwd)
        if self.password == hashlib.md5(pwd.encode()).hexdigest():
            self.password = generate_password_hash(pwd)
            db.session.commit()
            return True
        return False

    def set_password(self, pwd):
        self.password = generate_password_hash(pwd)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'nickname': self.nickname or self.username,
            'avatar': self.avatar,
            'role_id': self.role_id,
            'role_name': self.role.name if self.role else '',
            'role_level': self.role.level if self.role else 99,
            'is_agent': self.is_agent,
            'agent_level': self.agent_level,
            'parent_id': self.parent_id,
            'status': self.status,
            'tenant_id': self.tenant_id,
            'tenant_name': self.tenant.company_name if self.tenant else '主站',
            'id_card': self.id_card,
            'business_type': self.business_type,
            'business_type_name': {'both': '代练+陪玩', 'dailian': '专做代练', 'peiwan': '专做陪玩'}.get(self.business_type, '代练+陪玩'),
            'member_type': self.member_type,
            'member_type_name': {'internal': '内部成员', 'partner': '合作用户'}.get(self.member_type, '内部成员'),
            'commission_mode': self.commission_mode,
            'commission_mode_name': {'fixed': '固定金额', 'percent': '订单价百分比', 'profit_percent': '利润的百分比'}.get(self.commission_mode, '固定金额'),
            'commission_value': self.commission_value,
            'alipay_account': self.alipay_account,
            'alipay_name': self.alipay_name,
            'wechat_account': self.wechat_account,
            'wechat_qrcode': self.wechat_qrcode,
            'alipay_qrcode': self.alipay_qrcode,
            'grab_limit_dailian': self.grab_limit_dailian,
            'grab_limit_peiwan': self.grab_limit_peiwan,
            'grab_price_min': self.grab_price_min,
            'grab_price_max': self.grab_price_max,
            'live_url': self.live_url,
            'qq_wechat': self.qq_wechat,
            'phone': self.phone,
            'hire_date': self.hire_date,
            'mark': self.mark,
            'deposit': self.deposit,
            'no_sms': self.no_sms,
            'all_games': self.all_games,
            'game_permissions': self.game_permissions,
            'remark': self.remark,
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
    level = db.Column(db.Integer, default=99)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

    tenant = db.relationship('Tenant', backref='roles')

    def to_dict(self):

        return {
            'id': self.id,
            'name': self.name,
            'desc': self.desc,
            'permissions': json.loads(self.permissions) if self.permissions else [],
            'level': self.level,
            'tenant_id': self.tenant_id,
            'tenant_name': self.tenant.company_name if self.tenant else '主站',
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
    received_at = db.Column(db.DateTime, nullable=True)
    finished_at = db.Column(db.DateTime, nullable=True)
    platform_no = db.Column(db.String(100), default='')
    category = db.Column(db.String(50), default='')
    sub_category = db.Column(db.String(50), default='')
    tags = db.Column(db.String(255), default='')
    is_urgent = db.Column(db.Boolean, default=False)
    pay_status = db.Column(db.String(20), default='unpaid')
    real_amount = db.Column(db.Float, default=0)
    remark = db.Column(db.Text, default='')
    sales_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=True)
    parent_order_id = db.Column(db.Integer, nullable=True)
    from_tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=True)

    game = db.relationship('Game', backref='orders')
    area = db.relationship('GameArea', backref='orders')
    server = db.relationship('GameServer', backref='orders')
    source = db.relationship('Source', backref='orders')
    creator = db.relationship('User', foreign_keys=[creator_id], backref='created_orders')
    receiver = db.relationship('User', foreign_keys=[receiver_id], backref='received_orders')
    sales = db.relationship('User', foreign_keys=[sales_id])
    images = db.relationship('OrderImage', backref='order', cascade='all, delete-orphan')
    logs = db.relationship('OrderLog', backref='order', cascade='all, delete-orphan', order_by='OrderLog.created_at.desc()')
    tenant = db.relationship('Tenant', foreign_keys=[tenant_id], backref='orders')
    from_tenant = db.relationship('Tenant', foreign_keys=[from_tenant_id])

    def to_dict(self, mask_sensitive=False):
        received_at = get_order_received_at(self)
        d = {
            'id': self.id,
            'order_no': display_order_no(self),
            'raw_order_no': self.order_no,
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
            'source_id': self.source_id,
            'source_name': self.source.name if self.source else (Tenant.query.get(self.from_tenant_id).company_name if self.from_tenant_id and Tenant.query.get(self.from_tenant_id) else ''),
            'creator_name': self.creator.nickname or self.creator.username if self.creator else '',
            'receiver_id': self.receiver_id,
            'receiver_name': self.receiver.nickname or self.receiver.username if self.receiver else '',
            'is_priority': self.is_priority,
            'character_name': self.character_name,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else '',
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S') if self.updated_at else '',
            'received_at': format_datetime(received_at),
            'assigned_at': format_datetime(received_at),
            'finished_at': self.finished_at.strftime('%Y-%m-%d %H:%M:%S') if self.finished_at else '',
            'platform_no': self.platform_no,
            'category': self.category,
            'sub_category': self.sub_category,
            'tags': self.tags,
            'is_urgent': self.is_urgent,
            'pay_status': self.pay_status,
            'pay_status_name': {'unpaid': '未收款', 'paid': '已收款'}.get(self.pay_status, '未知'),
            'real_amount': self.real_amount,
            'remark': self.remark,
            'sales_id': self.sales_id,
            'sales_name': (self.sales.nickname or self.sales.username) if self.sales else '',
            'image_count': len(self.images),
            'is_new': (datetime.now() - self.created_at).total_seconds() < 3600 if self.created_at else False,
            'tenant_id': self.tenant_id,
            'tenant_name': self.tenant.company_name if self.tenant else '主站',
            'parent_order_id': self.parent_order_id,
            'from_tenant_id': self.from_tenant_id,
            'from_tenant_name': Tenant.query.get(self.from_tenant_id).company_name if self.from_tenant_id and Tenant.query.get(self.from_tenant_id) else '',
        }
        if mask_sensitive:
            d['amount'] = None
            d['real_amount'] = None
            d['pay_status'] = ''
            d['pay_status_name'] = ''
            d['source_name'] = ''
            d['sales_name'] = ''
            d['source_id'] = None
            d['sales_id'] = None
        return d


class OrderLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    content = db.Column(db.Text, default='')
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

    user = db.relationship('User', backref='order_logs')
    tenant = db.relationship('Tenant', backref='order_logs')

    def to_dict(self):
        return {
            'id': self.id,
            'order_id': self.order_id,
            'order_no': self.order.order_no if self.order else '',
            'user_id': self.user_id,
            'username': (self.user.nickname or self.user.username) if self.user else '系统',
            'content': self.content,
            'tenant_id': self.tenant_id,
            'tenant_name': self.tenant.company_name if self.tenant else '主站',
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else '',
        }


class Tenant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    prefix = db.Column(db.String(50), unique=True, nullable=False)
    company_name = db.Column(db.String(100), default='')
    logo = db.Column(db.String(255), default='')
    contact_name = db.Column(db.String(50), default='')
    contact_phone = db.Column(db.String(30), default='')
    domain = db.Column(db.String(100), default='')
    status = db.Column(db.String(20), default='normal')
    max_users = db.Column(db.Integer, default=10)
    max_orders = db.Column(db.Integer, default=1000)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    def to_dict(self):
        return {
            'id': self.id,
            'prefix': self.prefix,
            'company_name': self.company_name,
            'logo': self.logo,
            'contact_name': self.contact_name,
            'contact_phone': self.contact_phone,
            'domain': self.domain,
            'status': self.status,
            'max_users': self.max_users,
            'max_orders': self.max_orders,
            'user_count': User.query.filter_by(tenant_id=self.id).count(),
            'order_count': Order.query.filter_by(tenant_id=self.id).count(),
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else '',
        }


class OrderImage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    filename = db.Column(db.String(255), default='')
    filepath = db.Column(db.String(500), default='')
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

    tenant = db.relationship('Tenant', backref='order_images')

    def to_dict(self):
        url = '/uploads/' + self.filepath if self.filepath else ''
        token = request.args.get('token') if self.filepath else ''
        if url and token:
            url += '?token=' + token
        return {
            'id': self.id,
            'order_id': self.order_id,
            'filename': self.filename,
            'filepath': self.filepath,
            'url': url,
            'tenant_id': self.tenant_id,
            'tenant_name': self.tenant.company_name if self.tenant else '主站',
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else '',
        }


class Source(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    desc = db.Column(db.String(255), default='')
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

    tenant = db.relationship('Tenant', backref='sources')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'desc': self.desc,
            'tenant_id': self.tenant_id,
            'tenant_name': self.tenant.company_name if self.tenant else '主站',
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else '',
        }


class Game(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    icon = db.Column(db.String(255), default='')
    sort = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default='normal')
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

    areas = db.relationship('GameArea', backref='game', cascade='all, delete-orphan')
    tenant = db.relationship('Tenant', backref='games')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'icon': self.icon,
            'sort': self.sort,
            'status': self.status,
            'area_count': len(self.areas),
            'tenant_id': self.tenant_id,
            'tenant_name': self.tenant.company_name if self.tenant else '主站',
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else '',
        }


class GameArea(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    sort = db.Column(db.Integer, default=0)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

    servers = db.relationship('GameServer', backref='area', cascade='all, delete-orphan')
    tenant = db.relationship('Tenant', backref='game_areas')

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
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

    tenant = db.relationship('Tenant', backref='game_servers')

    def to_dict(self):
        return {
            'id': self.id,
            'area_id': self.area_id,
            'name': self.name,
            'sort': self.sort,
            'tenant_id': self.tenant_id,
            'tenant_name': self.tenant.company_name if self.tenant else '主站',
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else '',
        }


class AdminLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    action = db.Column(db.String(255), default='')
    url = db.Column(db.String(255), default='')
    ip = db.Column(db.String(50), default='')
    role_name = db.Column(db.String(50), default='')
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

    user = db.relationship('User', backref='logs')
    tenant = db.relationship('Tenant', backref='admin_logs')

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'username': self.user.nickname or self.user.username if self.user else '',
            'action': self.action,
            'url': self.url,
            'ip': self.ip,
            'role_name': self.role_name,
            'tenant_id': self.tenant_id,
            'tenant_name': self.tenant.company_name if self.tenant else '主站',
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else '',
        }


class Bill(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    bill_type = db.Column(db.String(20), default='player')
    amount = db.Column(db.Float, default=0)
    state = db.Column(db.String(20), default='unpaid')
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    settled_at = db.Column(db.DateTime, nullable=True)

    order = db.relationship('Order', backref='bills')
    user = db.relationship('User', backref='bills')
    tenant = db.relationship('Tenant', backref='bills')

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
            'order_state': order_dict.get('state', ''),
            'order_state_name': order_dict.get('state_name', ''),
            'image_count': order_dict.get('image_count', 0),
            'amount': self.amount,
            'state': self.state,
            'state_name': {'unpaid': '未结算', 'settling': '结算中', 'settled': '已结算'}.get(self.state, '未知'),
            'tenant_id': self.tenant_id,
            'tenant_name': self.tenant.company_name if self.tenant else '主站',
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else '',
            'settled_at': self.settled_at.strftime('%Y-%m-%d %H:%M:%S') if self.settled_at else '',
        }


class PlatformSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), nullable=False, unique=True)
    value = db.Column(db.Text, default='')
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=True)
    tenant = db.relationship('Tenant', backref='platform_settings')


class TenantBinding(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    parent_tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)
    child_tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    parent_tenant = db.relationship('Tenant', foreign_keys='TenantBinding.parent_tenant_id', backref='child_bindings')
    child_tenant = db.relationship('Tenant', foreign_keys='TenantBinding.child_tenant_id', backref='parent_bindings')

    def to_dict(self):
        return {
            'id': self.id,
            'parent_tenant_id': self.parent_tenant_id,
            'parent_tenant_name': self.parent_tenant.company_name if self.parent_tenant else '',
            'parent_tenant_prefix': self.parent_tenant.prefix if self.parent_tenant else '',
            'child_tenant_id': self.child_tenant_id,
            'child_tenant_name': self.child_tenant.company_name if self.child_tenant else '',
            'child_tenant_prefix': self.child_tenant.prefix if self.child_tenant else '',
            'status': self.status,
            'status_name': {'pending': '待确认', 'active': '已绑定', 'rejected': '已拒绝', 'disabled': '已禁用'}.get(self.status, '未知'),
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else '',
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S') if self.updated_at else '',
        }



def get_current_tenant():
    host = request.host.split(':')[0]
    parts = host.split('.')
    if len(parts) >= 3:
        prefix = parts[0]
        tenant = Tenant.query.filter_by(prefix=prefix, status='normal').first()
        return tenant
    return None


def apply_tenant_filter(query, model_class):
    tenant = get_current_tenant()
    if tenant and hasattr(model_class, 'tenant_id'):
        query = query.filter_by(tenant_id=tenant.id)
    return query


def check_tenant(obj):
    if not obj:
        return False
    tid = get_tenant_id()
    if tid is None:
        return True
    if not hasattr(obj, 'tenant_id'):
        return True
    return obj.tenant_id == tid


def get_tenant_id():
    tenant = get_current_tenant()
    return tenant.id if tenant else None


def is_normal_user(user):
    if not user or not user.role:
        return True
    return get_user_level(user) > 2


def get_user_permissions(user):
    if not user or not user.role or not user.role.permissions:
        return []
    try:
        return json.loads(user.role.permissions)
    except:
        return []


def user_has_permission(user, perm_id):
    perms = get_user_permissions(user)
    return 'system_admin' in perms or perm_id in perms


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
        if user.status != 'normal':
            if request.is_json or request.args.get('token'):
                return jsonify({'code': 0, 'msg': '账号已被禁用，请联系管理员'}), 401
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
        if get_user_level(user) > 2:
            return jsonify({'code': 0, 'msg': '你没有管理员权限，请重新登录'}), 403
        g.user = user
        return f(*args, **kwargs)
    return decorated


ROLE_LEVELS = {
    'system_admin': 1,
    'company_admin': 2,
    'customer_service': 3,
    'finance': 3,
    'player': 4,
}

PERM_MIN_LEVEL = {
    'auth_role': 1, 'auth_admin': 1, 'auth_adminlog': 1, 'company_source': 1,
    'tenant_manage': 1, 'tenant_binding': 1, 'system_maintain': 1,
    'platform_settings': 1, 'company_info': 1,
    'finance_bill': 2, 'game_manage': 2,
    'order_add': 2, 'order_ranking': 2,
    'order_all': 4, 'order_paidan': 4, 'order_qiangdan': 4,
    'order_stats': 4, 'order_logs': 4,
    'general_profile': 4, 'dashboard': 4,
}

def get_user_level(user):
    if not user or not user.role:
        return 99
    if user.role.level and user.role.level > 0:
        return user.role.level
    perms = get_user_permissions(user)
    min_lv = 99
    for p in perms:
        if p in ROLE_LEVELS:
            min_lv = min(min_lv, ROLE_LEVELS[p])
    return min_lv


def can_view_all_bills(user):
    if not user:
        return False
    if get_user_level(user) <= 2:
        return True
    return get_user_level(user) <= 3 and user_has_permission(user, 'finance_bill')


def get_user_game_ids(user):
    if not user or user.all_games or get_user_level(user) <= 2:
        return None
    try:
        game_ids = json.loads(user.game_permissions) if isinstance(user.game_permissions, str) else (user.game_permissions or [])
    except:
        game_ids = []
    result = []
    for gid in game_ids:
        try:
            result.append(int(gid))
        except:
            pass
    return result


def user_can_access_game(user, game_id):
    allowed = get_user_game_ids(user)
    if allowed is None:
        return True
    if not game_id:
        return False
    try:
        return int(game_id) in allowed
    except:
        return False


def apply_user_game_filter(query, user, model_class):
    allowed = get_user_game_ids(user)
    if allowed is None:
        return query
    if not allowed:
        return query.filter(model_class.game_id == -1)
    return query.filter(model_class.game_id.in_(allowed))


def check_order_game_access(order, user=None):
    user = user or g.user
    return user_can_access_game(user, order.game_id if order else None)


def order_readonly_for_user(order, user=None):
    user = user or g.user
    return bool(order and order.state == 6 and get_user_level(user) >= 4)


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
            user_level = get_user_level(user)
            perm_min = PERM_MIN_LEVEL.get(perm_id, 99)
            if 'system_admin' in perms or perm_id in perms or user_level <= perm_min:
                g.user = user
                return f(*args, **kwargs)
            return jsonify({'code': 0, 'msg': '你没有权限访问'}), 403
        return decorated
    return decorator


LOG_RATE_LIMITS = {
    'max_per_minute': 30,
    'max_per_hour': 200,
    'ban_threshold': 3,
}

_log_rate_lock = threading.Lock()
_log_rate_data = {}

PAGE_NAMES = {
    '/': '控制台', '/login': '登录页',
    '/companymaintain/rolemanage': '角色管理', '/companymaintain/adminmanage': '用户管理',
    '/companymaintain/sourcemanage': '来源管理', '/auth/adminlog': '管理员日志',
    '/game/manage': '游戏管理', '/companypaidan/index': '指派给我的订单',
    '/companyqiangdan/index': '内部抢单池', '/companyorder/index': '全部订单',
    '/companyorder/add': '录单', '/Companyobill/userlist': '收益管理',
    '/general/profile': '个人资料', '/tenant_manage': '租户管理',
    '/tenant_binding': '绑定上家', '/company_info': '企业信息',
    '/platform_settings': '平台设置', '/system_maintain': '系统维护',
    '/companyorder/ranking': '接单员排行', '/order_stats': '订单统计',
    '/order_logs': '订单日志', '/order_detail': '订单详情',
}

API_ACTION_NAMES = {
    '/api/roles': '操作角色', '/api/users': '操作用户', '/api/orders': '操作订单',
    '/api/sources': '操作来源', '/api/games': '操作游戏', '/api/bills': '操作账单',
    '/api/admin_logs': '查看日志', '/api/tenant': '操作租户', '/api/platform_settings': '修改平台设置',
    '/api/brand': '查看品牌', '/api/upload': '上传文件', '/api/backup': '备份数据',
}


def _check_rate_limit(user_id):
    now = datetime.now()
    with _log_rate_lock:
        if user_id not in _log_rate_data:
            _log_rate_data[user_id] = {'minute': [], 'hour': [], 'violations': 0}
        data = _log_rate_data[user_id]
        data['minute'] = [t for t in data['minute'] if (now - t).total_seconds() < 60]
        data['hour'] = [t for t in data['hour'] if (now - t).total_seconds() < 3600]
        if len(data['minute']) >= LOG_RATE_LIMITS['max_per_minute']:
            data['violations'] += 1
            if data['violations'] >= LOG_RATE_LIMITS['ban_threshold']:
                user = User.query.get(user_id)
                if user and user.status == 'normal':
                    user.status = 'hidden'
                    db.session.commit()
                return 'banned'
            return 'rate_limited'
        if len(data['hour']) >= LOG_RATE_LIMITS['max_per_hour']:
            data['violations'] += 1
            if data['violations'] >= LOG_RATE_LIMITS['ban_threshold']:
                user = User.query.get(user_id)
                if user and user.status == 'normal':
                    user.status = 'hidden'
                    db.session.commit()
                return 'banned'
            return 'rate_limited'
        data['minute'].append(now)
        data['hour'].append(now)
        if len(data['minute']) < LOG_RATE_LIMITS['max_per_minute'] // 2:
            data['violations'] = max(0, data['violations'] - 1)
    return 'ok'


def add_log(action, url=''):
    user = getattr(g, 'user', None)
    if user:
        rn = user.role.name if user.role else ''
        tid = get_tenant_id()
        log = AdminLog(user_id=user.id, action=action, url=url, ip=request.remote_addr, role_name=rn, tenant_id=tid)
        db.session.add(log)
        db.session.commit()
        _check_rate_limit(user.id)


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


def display_order_no(order):
    if not order:
        return ''
    if order.order_no and order.order_no.startswith('拆'):
        return order.order_no
    return order.platform_no or order.order_no or ''


def order_no_exists(order_no):
    if not order_no:
        return False
    return Order.query.filter(db.or_(Order.order_no == order_no, Order.platform_no == order_no)).first() is not None


def format_datetime(value):
    return value.strftime('%Y-%m-%d %H:%M:%S') if value else ''


def get_order_received_at(order):
    if not order:
        return None
    if getattr(order, 'received_at', None):
        return order.received_at
    if not order.receiver_id:
        return None
    log = OrderLog.query.filter_by(order_id=order.id).filter(db.or_(
        OrderLog.content.contains('接手'),
        OrderLog.content.contains('指派')
    )).order_by(OrderLog.created_at.asc()).first()
    if log:
        return log.created_at
    return order.updated_at or order.created_at


BILL_STATE_NAMES = {'unpaid': '未结算', 'settling': '结算中', 'settled': '已结算'}


def get_group_bill_state(bills):
    states = [(bill.state or 'unpaid') for bill in bills]
    if states and all(state == 'settled' for state in states):
        return 'settled'
    if any(state == 'settled' for state in states) or any(state == 'settling' for state in states):
        return 'settling'
    return 'unpaid'


def get_order_settlement_info(order):
    if not order:
        return {'state': 'unpaid', 'state_name': BILL_STATE_NAMES['unpaid'], 'amount': 0, 'settled_at': ''}
    bills = Bill.query.filter_by(order_id=order.id).all()
    state = get_group_bill_state(bills)
    settled_times = [bill.settled_at for bill in bills if bill.settled_at]
    return {
        'state': state,
        'state_name': BILL_STATE_NAMES.get(state, '未知'),
        'amount': round(float(sum((bill.amount or 0) for bill in bills)), 2),
        'settled_at': format_datetime(max(settled_times)) if state == 'settled' and settled_times else '',
    }


def sync_order_bills(order):
    if not order or order.state != 6:
        return
    if order.receiver_id:
        bill = Bill.query.filter_by(order_id=order.id, bill_type='player').first()
        if not bill:
            bill = Bill(order_id=order.id, bill_type='player', state='unpaid', tenant_id=order.tenant_id)
            db.session.add(bill)
        if bill.state != 'settled':
            bill.user_id = order.receiver_id
            bill.amount = order.cost or 0
            bill.tenant_id = order.tenant_id
    service_amount = round(float(order.amount or 0) - float(order.cost or 0), 2)
    if order.creator_id and order.creator_id != order.receiver_id:
        bill = Bill.query.filter_by(order_id=order.id, bill_type='service').first()
        if not bill:
            bill = Bill(order_id=order.id, bill_type='service', state='unpaid', tenant_id=order.tenant_id)
            db.session.add(bill)
        if bill.state != 'settled':
            bill.user_id = order.creator_id
            bill.amount = service_amount
            bill.tenant_id = order.tenant_id


def sync_completed_order_bills():
    q = apply_tenant_filter(Order.query.filter_by(state=6), Order)
    for order in q.all():
        sync_order_bills(order)
    db.session.commit()


def build_grouped_bill_rows(bills):
    grouped = {}
    ordered_keys = []
    for bill in bills:
        key = ('order', bill.order_id) if bill.order_id else ('bill', bill.id)
        if key not in grouped:
            grouped[key] = []
            ordered_keys.append(key)
        grouped[key].append(bill)

    rows = []
    for key in ordered_keys:
        group = grouped[key]
        first = group[0]
        if not first.order:
            continue
        row = first.to_dict()
        settlement = get_order_settlement_info(first.order) if first.order else None
        group_state = settlement['state'] if settlement else get_group_bill_state(group)
        bill_types = {bill.bill_type for bill in group}
        settled_times = [bill.settled_at for bill in group if bill.settled_at]
        row['id'] = first.id
        row['bill_ids'] = [bill.id for bill in group]
        row['amount'] = round(float(sum((bill.amount or 0) for bill in group)), 2)
        row['state'] = group_state
        row['state_name'] = settlement['state_name'] if settlement else BILL_STATE_NAMES.get(group_state, '未知')
        row['bill_type'] = first.bill_type if len(bill_types) == 1 else 'mixed'
        row['bill_type_name'] = row.get('bill_type_name', '') if len(bill_types) == 1 else '收益汇总'
        row['settled_at'] = settlement['settled_at'] if settlement else (format_datetime(max(settled_times)) if group_state == 'settled' and settled_times else '')
        rows.append(row)
    return rows


# ============ 页面路由 ============

@app.before_request
def before_request_log():
    if request.method not in ('GET', 'POST'):
        return
    path = request.path
    if path.startswith('/static/') or path.startswith('/favicon'):
        return
    if path.startswith('/api/'):
        return
    user = get_current_user()
    if not user:
        return
    if user.status != 'normal':
        return
    page_name = PAGE_NAMES.get(path, '')
    if not page_name:
        for p, n in PAGE_NAMES.items():
            if path.startswith(p) and p != '/':
                page_name = n
                break
    if page_name:
        rn = user.role.name if user.role else ''
        tid = get_tenant_id()
        log = AdminLog(user_id=user.id, action=f'访问页面：{page_name}', url=path, ip=request.remote_addr, role_name=rn, tenant_id=tid)
        db.session.add(log)
        db.session.commit()
        _check_rate_limit(user.id)

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
    tenant = get_current_tenant()
    q = User.query.filter_by(username=username)
    if tenant:
        q = q.filter_by(tenant_id=tenant.id)
    else:
        q = q.filter_by(tenant_id=None)
    user = q.first()
    if not user or not user.check_password(password):
        return jsonify({'code': 0, 'msg': '用户名或密码错误'})
    if user.status != 'normal':
        return jsonify({'code': 0, 'msg': '账号已被禁用'})
    token_str = uuid.uuid4().hex + uuid.uuid4().hex
    lt = LoginToken(token=token_str, user_id=user.id, expires_at=datetime.now() + timedelta(days=7))
    db.session.add(lt)
    user.last_login = datetime.now()
    rn = user.role.name if user.role else ''
    tid = tenant.id if tenant else None
    log = AdminLog(user_id=user.id, action='登录系统', ip=request.remote_addr, role_name=rn, tenant_id=tid)
    db.session.add(log)
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
            'role_level': user.role.level if user.role else 99,
            'last_login': user.last_login.strftime('%Y-%m-%d %H:%M:%S') if user.last_login else '',
            'created_at': user.created_at.strftime('%Y-%m-%d %H:%M:%S') if user.created_at else '',
            'permissions': perms,
            'permission_tree': PERMISSION_TREE,
        }
    })


@app.route('/logout')
def logout():
    return redirect(url_for('login'))


@app.route('/companymaintain/rolemanage')
@login_required
@perm_required('auth_role')
def role_manage():
    return render_template('role_manage.html')


@app.route('/companymaintain/adminmanage')
@login_required
@perm_required('auth_admin')
def admin_manage():
    return render_template('admin_manage.html')


@app.route('/companymaintain/sourcemanage')
@login_required
@perm_required('company_source')
def source_manage():
    return render_template('source_manage.html')


@app.route('/gamemanage/index')
@login_required
@perm_required('game_manage')
def game_manage():
    return render_template('game_manage.html')


@app.route('/companypaidan/index')
@login_required
@perm_required('order_paidan')
def paidan_index():
    return render_template('paidan.html')


@app.route('/companyqiangdan/index')
@login_required
@perm_required('order_qiangdan')
def qiangdan_index():
    return render_template('qiangdan.html')


@app.route('/companyorder/index')
@login_required
@perm_required('order_all')
def order_index():
    return render_template('order_all.html')


@app.route('/companyorder/add')
@login_required
@perm_required('order_add')
def order_add():
    return render_template('order_add.html')


@app.route('/Companyobill/userlist')
@login_required
@perm_required('finance_bill')
def bill_userlist():
    return render_template('bill.html')


@app.route('/general/profile')
@login_required
def profile():
    return render_template('profile.html')


@app.route('/auth/adminlog')
@login_required
@perm_required('auth_adminlog')
def admin_log():
    return render_template('admin_log.html')


@app.route('/tenant_manage')
@login_required
@perm_required('tenant_manage')
def tenant_manage():
    return render_template('tenant_manage.html')

@app.route('/tenant_binding')
@login_required
@perm_required('tenant_binding')
def tenant_binding():
    return render_template('tenant_binding.html')

@app.route('/company_info')
@login_required
@perm_required('company_info')
def company_info():
    return render_template('company_info.html')

@app.route('/platform_settings')
@login_required
@perm_required('platform_settings')
def platform_settings():
    return render_template('platform_settings.html')


@app.route('/api/platform_settings', methods=['GET'])
@login_required
def api_platform_settings_get():
    tid = get_tenant_id()
    settings = PlatformSetting.query.filter_by(tenant_id=tid).all()
    result = {}
    for s in settings:
        result[s.key] = s.value
    return jsonify({'code': 1, 'data': result})


@app.route('/api/platform_settings', methods=['POST'])
@login_required
@perm_required('platform_settings')
def api_platform_settings_save():
    data = request.get_json()
    tid = get_tenant_id()
    for k, v in data.items():
        s = PlatformSetting.query.filter_by(key=k, tenant_id=tid).first()
        if s:
            s.value = v if isinstance(v, str) else json.dumps(v)
        else:
            db.session.add(PlatformSetting(key=k, value=v if isinstance(v, str) else json.dumps(v), tenant_id=tid))
    db.session.commit()
    changes = [f'{k}={v}' for k, v in data.items()]
    add_log(f'保存平台设置: {", ".join(changes)}', '/api/platform_settings')
    return jsonify({'code': 1, 'msg': '保存成功'})

@app.route('/system_maintain')
@login_required
@perm_required('system_maintain')
def system_maintain():
    return render_template('system_maintain.html')

@app.route('/order_ranking')
@login_required
@perm_required('order_ranking')
def order_ranking():
    return render_template('order_ranking.html')

@app.route('/order_stats')
@login_required
@perm_required('order_stats')
def order_stats():
    return render_template('order_stats.html')

@app.route('/order_logs')
@login_required
@perm_required('order_logs')
def order_logs():
    return render_template('order_logs.html')

@app.route('/order_detail')
@login_required
def order_detail():
    return render_template('order_detail.html')


# ============ API路由 ============

@app.route('/api/roles', methods=['GET'])
@login_required
def api_roles():
    q = Role.query
    q = apply_tenant_filter(q, Role)
    roles = q.all()
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
    role = Role(name=data.get('name', ''), desc=data.get('desc', ''), permissions=json.dumps(data.get('permissions', [])), tenant_id=get_tenant_id())
    db.session.add(role)
    db.session.commit()
    add_log(f'新增角色: {role.name}', '/api/roles')
    return jsonify({'code': 1, 'msg': '添加成功'})


@app.route('/api/roles/<int:rid>', methods=['PUT'])
@admin_required
def api_role_edit(rid):
    role = Role.query.get_or_404(rid)
    if not check_tenant(role): return jsonify({'code': 0, 'msg': '无权操作'})
    data = request.get_json()
    import json
    old_name, old_desc, old_perms = role.name, role.desc, role.permissions
    role.name = data.get('name', role.name)
    role.desc = data.get('desc', role.desc)
    role.permissions = json.dumps(data.get('permissions', json.loads(role.permissions)))
    db.session.commit()
    changes = []
    if old_name != role.name: changes.append(f'名称: {old_name} → {role.name}')
    if old_desc != role.desc: changes.append(f'描述: {old_desc} → {role.desc}')
    old_p = set(json.loads(old_perms)) if old_perms else set()
    new_p = set(json.loads(role.permissions)) if role.permissions else set()
    if old_p != new_p:
        added = new_p - old_p
        removed = old_p - new_p
        parts = []
        if added: parts.append(f'新增[{",".join(added)}]')
        if removed: parts.append(f'移除[{",".join(removed)}]')
        changes.append(f'权限: {", ".join(parts)}')
    add_log(f'修改角色: {role.name}, {", ".join(changes) if changes else "无实际变更"}', f'/api/roles/{rid}')
    return jsonify({'code': 1, 'msg': '修改成功'})


@app.route('/api/roles/<int:rid>', methods=['DELETE'])
@admin_required
def api_role_del(rid):
    role = Role.query.get_or_404(rid)
    if not check_tenant(role): return jsonify({'code': 0, 'msg': '无权操作'})
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
    game_id = request.args.get('game_id', type=int)
    q = User.query
    q = apply_tenant_filter(q, User)

    current_user = g.user
    user_level = get_user_level(current_user)
    bill_scope = request.args.get('scope') == 'bill' and can_view_all_bills(current_user)
    if game_id and not user_can_access_game(current_user, game_id):
        return jsonify({'code': 0, 'msg': '无权访问该游戏'}), 403
    if is_normal_user(current_user) and not bill_scope and not (game_id and user_level == 3):
        tree_ids = get_user_tree_ids(current_user.id)
        q = q.filter(User.id.in_(tree_ids))

    if keyword:
        q = q.filter(db.or_(User.username.contains(keyword), User.nickname.contains(keyword), User.phone.contains(keyword), User.id_card.contains(keyword), User.qq_wechat.contains(keyword)))
    if game_id:
        matched_users = [u for u in q.all() if user_can_access_game(u, game_id)]
        total = len(matched_users)
        users = matched_users[(page - 1) * limit:page * limit]
    else:
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
    if not data.get('role_id'):
        return jsonify({'code': 0, 'msg': '角色职位不能为空'})
    tid = get_tenant_id()
    if User.query.filter_by(username=username, tenant_id=tid).first():
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
    user.tenant_id = get_tenant_id()
    for k in ['id_card', 'business_type', 'member_type', 'commission_mode',
              'alipay_account', 'alipay_name', 'wechat_account', 'wechat_qrcode', 'alipay_qrcode',
              'live_url', 'qq_wechat', 'phone', 'hire_date', 'mark', 'remark']:
        if k in data:
            setattr(user, k, data[k])
    for k in ['commission_value', 'deposit', 'grab_price_min', 'grab_price_max']:
        if k in data:
            setattr(user, k, float(data[k]) if data[k] else 0)
    for k in ['grab_limit_dailian', 'grab_limit_peiwan']:
        if k in data:
            setattr(user, k, int(data[k]) if data[k] else 0)
    for k in ['no_sms', 'all_games']:
        if k in data:
            setattr(user, k, bool(data[k]))
    if 'game_permissions' in data:
        user.game_permissions = json.dumps(data['game_permissions']) if isinstance(data['game_permissions'], list) else data['game_permissions']
    db.session.add(user)
    db.session.commit()
    field_names = {'nickname':'名称','role_id':'角色','business_type':'业务类型','member_type':'成员类型',
        'commission_mode':'提成模式','commission_value':'提成金额','id_card':'身份证','status':'状态',
        'alipay_account':'支付宝账号','alipay_name':'支付宝姓名','alipay_qrcode':'支付宝收款码',
        'wechat_account':'微信账号','wechat_qrcode':'微信收款码',
        'grab_limit_dailian':'抢代练上限','grab_limit_peiwan':'抢陪玩上限',
        'grab_price_min':'最低价','grab_price_max':'最高价','live_url':'直播地址',
        'qq_wechat':'QQ/微信','phone':'电话','hire_date':'入职日期','mark':'标记',
        'deposit':'保证金','no_sms':'不发短信','game_permissions':'游戏权限','all_games':'全部游戏','remark':'备注'}
    defaults = {'status':'normal','business_type':'both','member_type':'internal','commission_mode':'fixed',
        'commission_value':0,'deposit':0,'grab_limit_dailian':0,'grab_limit_peiwan':0,
        'grab_price_min':0,'grab_price_max':99999,'no_sms':False,'all_games':False}
    parts = []
    for k, v in data.items():
        if k in ('username','password') or k not in field_names: continue
        if k in defaults and data[k] == defaults[k]: continue
        label = field_names.get(k, k)
        if k == 'game_permissions' and isinstance(v, list):
            names = [g.name for g in Game.query.filter(Game.id.in_(v)).all()] if v else []
            parts.append(f'{label}={", ".join(names) if names else "无"}')
        elif k == 'role_id' and v:
            role = Role.query.get(v)
            parts.append(f'{label}={role.name if role else v}')
        else:
            parts.append(f'{label}={v}')
    detail = ', '.join(parts) if parts else '默认配置'
    add_log(f'新增用户: {username}, {detail}')
    return jsonify({'code': 1, 'msg': '新增成功', 'data': {'id': user.id}})


@app.route('/api/users/<int:uid>', methods=['PUT'])
@admin_required
def api_user_edit(uid):
    user = User.query.get_or_404(uid)
    if not check_tenant(user): return jsonify({'code': 0, 'msg': '无权操作'})
    data = request.get_json()
    current_user = g.user
    field_names = {'nickname':'名称','role_id':'角色','status':'状态','is_agent':'代理','agent_level':'代理等级',
        'parent_id':'上级代理','id_card':'身份证','business_type':'业务类型','member_type':'成员类型',
        'commission_mode':'提成模式','commission_value':'提成金额',
        'alipay_account':'支付宝账号','alipay_name':'支付宝姓名','alipay_qrcode':'支付宝收款码',
        'wechat_account':'微信账号','wechat_qrcode':'微信收款码',
        'grab_limit_dailian':'抢代练上限','grab_limit_peiwan':'抢陪玩上限',
        'grab_price_min':'最低价','grab_price_max':'最高价','live_url':'直播地址',
        'qq_wechat':'QQ/微信','phone':'电话','hire_date':'入职日期','mark':'标记',
        'deposit':'保证金','no_sms':'不发短信','game_permissions':'游戏权限','all_games':'全部游戏','remark':'备注'}
    num_fields = {'commission_value','deposit','grab_price_min','grab_price_max'}
    int_fields = {'grab_limit_dailian','grab_limit_peiwan'}
    bool_fields = {'no_sms','all_games'}
    snapshot = {}
    for k in field_names:
        snapshot[k] = getattr(user, k, None)
    if 'password' in data and data['password']:
        if user.id != current_user.id:
            target_is_admin = user.role and 'system_admin' in (json.loads(user.role.permissions) if user.role.permissions else [])
            if target_is_admin:
                return jsonify({'code': 0, 'msg': '不能修改其他系统管理员的密码'})
        user.set_password(data['password'])
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
    for k in ['id_card', 'business_type', 'member_type', 'commission_mode',
              'alipay_account', 'alipay_name', 'wechat_account', 'wechat_qrcode', 'alipay_qrcode',
              'live_url', 'qq_wechat', 'phone', 'hire_date', 'mark', 'remark']:
        if k in data:
            setattr(user, k, data[k])
    for k in num_fields:
        if k in data:
            setattr(user, k, float(data[k]) if data[k] not in (None, '') else 0)
    for k in int_fields:
        if k in data:
            setattr(user, k, int(data[k]) if data[k] not in (None, '') else 0)
    for k in bool_fields:
        if k in data:
            setattr(user, k, bool(data[k]))
    if 'game_permissions' in data:
        user.game_permissions = json.dumps(data['game_permissions']) if isinstance(data['game_permissions'], list) else data['game_permissions']
    db.session.commit()
    changes = []
    for k in data:
        if k not in field_names: continue
        label = field_names[k]
        old_val = snapshot[k]
        new_val = data[k]
        if k == 'game_permissions':
            old_ids = json.loads(old_val) if old_val else []
            new_ids = new_val if isinstance(new_val, list) else json.loads(new_val) if new_val else []
            if set(map(str, old_ids)) == set(map(str, new_ids)): continue
            old_names = [g.name for g in Game.query.filter(Game.id.in_([int(x) for x in old_ids])).all()] if old_ids else []
            new_names = [g.name for g in Game.query.filter(Game.id.in_([int(x) for x in new_ids])).all()] if new_ids else []
            changes.append(f'{label}: [{", ".join(old_names) or "无"}] → [{", ".join(new_names) or "无"}]')
        elif k == 'role_id':
            if str(old_val) == str(new_val): continue
            old_role = Role.query.get(old_val).name if old_val and Role.query.get(int(old_val)) else '无'
            new_role = Role.query.get(new_val).name if new_val and Role.query.get(int(new_val)) else '无'
            changes.append(f'{label}: {old_role} → {new_role}')
        elif k in num_fields:
            old_f = float(old_val) if old_val not in (None, '') else 0
            new_f = float(new_val) if new_val not in (None, '') else 0
            if old_f == new_f: continue
            changes.append(f'{label}: {old_f} → {new_f}')
        elif k in int_fields:
            old_i = int(old_val) if old_val not in (None, '') else 0
            new_i = int(new_val) if new_val not in (None, '') else 0
            if old_i == new_i: continue
            changes.append(f'{label}: {old_i} → {new_i}')
        elif k in bool_fields:
            old_b = bool(old_val)
            new_b = bool(new_val)
            if old_b == new_b: continue
            changes.append(f'{label}: {"是" if old_b else "否"} → {"是" if new_b else "否"}')
        else:
            if str(old_val) == str(new_val): continue
            changes.append(f'{label}: {old_val} → {new_val}')
    detail = ', '.join(changes) if changes else '无实际变更'
    add_log(f'修改用户: {user.username}, {detail}', f'/api/users/{uid}')
    return jsonify({'code': 1, 'msg': '修改成功'})


@app.route('/api/users/<int:uid>', methods=['DELETE'])
@admin_required
def api_user_del(uid):
    user = User.query.get_or_404(uid)
    if not check_tenant(user): return jsonify({'code': 0, 'msg': '无权操作'})
    cascade_delete(uid)
    db.session.delete(user)
    db.session.commit()
    add_log(f'删除用户: {user.username}(昵称={user.nickname}, 角色={user.role.name if user.role else "无"}, 代理={"L"+str(user.agent_level) if user.is_agent else "否"})', f'/api/users/{uid}')
    return jsonify({'code': 1, 'msg': '删除成功'})


@app.route('/api/users/<int:uid>/set_agent', methods=['POST'])
@admin_required
def api_user_set_agent(uid):
    user = User.query.get_or_404(uid)
    if not check_tenant(user): return jsonify({'code': 0, 'msg': '无权操作'})
    data = request.get_json()
    old_agent, old_level, old_parent = user.is_agent, user.agent_level, user.parent_id
    user.is_agent = data.get('is_agent', not user.is_agent)
    user.agent_level = data.get('agent_level', user.agent_level)
    if 'parent_id' in data:
        user.parent_id = data['parent_id']
    db.session.commit()
    changes = []
    if old_agent != user.is_agent: changes.append(f'代理: {"否" if old_agent else "是"} → {"是" if user.is_agent else "否"}')
    if old_level != user.agent_level: changes.append(f'等级: L{old_level} → L{user.agent_level}')
    if old_parent != user.parent_id:
        old_pn = (User.query.get(old_parent).nickname or User.query.get(old_parent).username) if old_parent and User.query.get(old_parent) else '无'
        new_pn = (User.query.get(user.parent_id).nickname or User.query.get(user.parent_id).username) if user.parent_id and User.query.get(user.parent_id) else '无'
        changes.append(f'上级: {old_pn} → {new_pn}')
    add_log(f'设置代理: {user.username}, {", ".join(changes) if changes else "无变更"}', f'/api/users/{uid}/set_agent')
    return jsonify({'code': 1, 'msg': '设置成功'})


@app.route('/api/sources', methods=['GET'])
@login_required
def api_sources():
    sources = apply_tenant_filter(Source.query, Source).all()
    return jsonify({'code': 0, 'data': [s.to_dict() for s in sources], 'count': len(sources)})


@app.route('/api/sources', methods=['POST'])
@login_required
def api_source_add():
    data = request.get_json()
    source = Source(name=data.get('name', ''), desc=data.get('desc', ''), tenant_id=get_tenant_id())
    db.session.add(source)
    db.session.commit()
    add_log(f'新增来源: {source.name}', '/api/sources')
    return jsonify({'code': 1, 'msg': '添加成功'})


@app.route('/api/sources/<int:sid>', methods=['PUT'])
@login_required
def api_source_edit(sid):
    source = Source.query.get_or_404(sid)
    if not check_tenant(source): return jsonify({'code': 0, 'msg': '无权操作'})
    data = request.get_json()
    old_name, old_desc = source.name, source.desc
    source.name = data.get('name', source.name)
    source.desc = data.get('desc', source.desc)
    db.session.commit()
    changes = []
    if old_name != source.name: changes.append(f'名称: {old_name} → {source.name}')
    if old_desc != source.desc: changes.append(f'描述: {old_desc} → {source.desc}')
    if changes: add_log(f'修改来源: {source.name}, {", ".join(changes)}', f'/api/sources/{sid}')
    return jsonify({'code': 1, 'msg': '修改成功'})


@app.route('/api/sources/<int:sid>', methods=['DELETE'])
@login_required
def api_source_del(sid):
    source = Source.query.get_or_404(sid)
    if not check_tenant(source): return jsonify({'code': 0, 'msg': '无权操作'})
    db.session.delete(source)
    db.session.commit()
    add_log(f'删除来源: {source.name}', f'/api/sources/{sid}')
    return jsonify({'code': 1, 'msg': '删除成功'})

@app.route('/api/games', methods=['GET'])
@login_required
def api_games():
    q = apply_tenant_filter(Game.query, Game)
    allowed = get_user_game_ids(g.user)
    if allowed is not None:
        q = q.filter(Game.id.in_(allowed) if allowed else Game.id == -1)
    games = q.order_by(Game.sort, Game.id).all()
    return jsonify({'code': 0, 'data': [g.to_dict() for g in games], 'count': len(games)})


@app.route('/api/games', methods=['POST'])
@login_required
def api_game_add():
    data = request.get_json()
    game = Game(name=data.get('name', ''), icon=data.get('icon', ''), sort=data.get('sort', 0), tenant_id=get_tenant_id())
    db.session.add(game)
    db.session.commit()
    add_log(f'新增游戏: {game.name}', '/api/games')
    return jsonify({'code': 1, 'msg': '添加成功'})


@app.route('/api/games/<int:gid>', methods=['PUT'])
@login_required
def api_game_edit(gid):
    game = Game.query.get_or_404(gid)
    if not check_tenant(game): return jsonify({'code': 0, 'msg': '无权操作'})
    data = request.get_json()
    old_name, old_icon, old_sort, old_status = game.name, game.icon, game.sort, game.status
    game.name = data.get('name', game.name)
    game.icon = data.get('icon', game.icon)
    game.sort = data.get('sort', game.sort)
    game.status = data.get('status', game.status)
    db.session.commit()
    changes = []
    if old_name != game.name: changes.append(f'名称: {old_name} → {game.name}')
    if old_icon != game.icon: changes.append(f'图标: {old_icon} → {game.icon}')
    if old_sort != game.sort: changes.append(f'排序: {old_sort} → {game.sort}')
    if old_status != game.status: changes.append(f'状态: {old_status} → {game.status}')
    if changes: add_log(f'修改游戏: {game.name}, {", ".join(changes)}', f'/api/games/{gid}')
    return jsonify({'code': 1, 'msg': '修改成功'})


@app.route('/api/games/<int:gid>', methods=['DELETE'])
@login_required
def api_game_del(gid):
    game = Game.query.get_or_404(gid)
    if not check_tenant(game): return jsonify({'code': 0, 'msg': '无权操作'})
    db.session.delete(game)
    db.session.commit()
    add_log(f'删除游戏: {game.name}', f'/api/games/{gid}')
    return jsonify({'code': 1, 'msg': '删除成功'})
@login_required
def api_game_areas(gid):
    if not user_can_access_game(g.user, gid):
        return jsonify({'code': 0, 'msg': '无权访问该游戏'}), 403
    q = GameArea.query.filter_by(game_id=gid)
    q = apply_tenant_filter(q, GameArea)
    areas = q.order_by(GameArea.sort, GameArea.id).all()
    return jsonify({'code': 0, 'data': [a.to_dict() for a in areas], 'count': len(areas)})


@app.route('/api/games/<int:gid>/areas', methods=['POST'])
@login_required
def api_game_area_add(gid):
    data = request.get_json()
    area = GameArea(game_id=gid, name=data.get('name', ''), sort=data.get('sort', 0), tenant_id=get_tenant_id())
    db.session.add(area)
    db.session.commit()
    return jsonify({'code': 1, 'msg': '添加成功'})


@app.route('/api/game_areas/<int:aid>', methods=['PUT'])
@login_required
def api_game_area_edit(aid):
    area = GameArea.query.get_or_404(aid)
    if not check_tenant(area): return jsonify({'code': 0, 'msg': '无权操作'})
    data = request.get_json()
    area.name = data.get('name', area.name)
    area.sort = data.get('sort', area.sort)
    db.session.commit()
    return jsonify({'code': 1, 'msg': '修改成功'})


@app.route('/api/game_areas/<int:aid>', methods=['DELETE'])
@login_required
def api_game_area_del(aid):
    area = GameArea.query.get_or_404(aid)
    if not check_tenant(area): return jsonify({'code': 0, 'msg': '无权操作'})
    db.session.delete(area)
    db.session.commit()
    return jsonify({'code': 1, 'msg': '删除成功'})


@app.route('/api/game_areas/<int:aid>/servers', methods=['GET'])
@login_required
def api_area_servers(aid):
    q = GameServer.query.filter_by(area_id=aid)
    q = apply_tenant_filter(q, GameServer)
    servers = q.order_by(GameServer.sort, GameServer.id).all()
    return jsonify({'code': 0, 'data': [s.to_dict() for s in servers], 'count': len(servers)})


@app.route('/api/game_areas/<int:aid>/servers', methods=['POST'])
@login_required
def api_area_server_add(aid):
    data = request.get_json()
    srv = GameServer(area_id=aid, name=data.get('name', ''), sort=data.get('sort', 0), tenant_id=get_tenant_id())
    db.session.add(srv)
    db.session.commit()
    return jsonify({'code': 1, 'msg': '添加成功'})


@app.route('/api/game_servers/<int:sid>', methods=['PUT'])
@login_required
def api_game_server_edit(sid):
    srv = GameServer.query.get_or_404(sid)
    if not check_tenant(srv): return jsonify({'code': 0, 'msg': '无权操作'})
    data = request.get_json()
    srv.name = data.get('name', srv.name)
    srv.sort = data.get('sort', srv.sort)
    db.session.commit()
    return jsonify({'code': 1, 'msg': '修改成功'})


@app.route('/api/game_servers/<int:sid>', methods=['DELETE'])
@login_required
def api_game_server_del(sid):
    srv = GameServer.query.get_or_404(sid)
    if not check_tenant(srv): return jsonify({'code': 0, 'msg': '无权操作'})
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
    q = apply_tenant_filter(q, Order)

    current_user = g.user
    view = request.args.get('view', 'all')
    user_level = get_user_level(current_user)
    if user_level >= 4 and view != 'qiangdan':
        q = q.filter(db.or_(Order.creator_id == current_user.id, Order.receiver_id == current_user.id))
    q = apply_user_game_filter(q, current_user, Order)

    if state != '':
        if ',' in state:
            q = q.filter(Order.state.in_([int(s) for s in state.split(',')]))
        else:
            q = q.filter_by(state=int(state))
    if keyword:
        q = q.filter((Order.order_no.contains(keyword)) | (Order.platform_no.contains(keyword)) | (Order.character_name.contains(keyword)))
    if game_id:
        q = q.filter_by(game_id=int(game_id))
    if order_type != '':
        q = q.filter_by(order_type=int(order_type))
    if view == 'paidan':
        q = q.filter(Order.receiver_id == current_user.id, Order.state.in_([3, 4, 5, 6, 12]))
    elif view == 'qiangdan':
        q = q.filter_by(state=2)
    source_id = request.args.get('source_id', '')
    receiver_id = request.args.get('receiver_id', '')
    sales_id = request.args.get('sales_id', '')
    pay_status = request.args.get('pay_status', '')
    is_urgent = request.args.get('is_urgent', '')
    platform_no = request.args.get('platform_no', '')
    category = request.args.get('category', '')
    if source_id:
        q = q.filter_by(source_id=int(source_id))
    if receiver_id:
        q = q.filter_by(receiver_id=int(receiver_id))
    if sales_id:
        q = q.filter_by(sales_id=int(sales_id))
    if pay_status:
        pay_map = {'0': 'unpaid', '1': 'paid', 'unpaid': 'unpaid', 'paid': 'paid'}
        q = q.filter_by(pay_status=pay_map.get(pay_status, pay_status))
    if is_urgent != '':
        q = q.filter_by(is_urgent=is_urgent == '1')
    if platform_no:
        q = q.filter(Order.platform_no.contains(platform_no))
    if category:
        q = q.filter_by(category=category)
    character_name = request.args.get('character_name', '')
    if character_name:
        q = q.filter(Order.character_name.contains(character_name))
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    if date_from:
        q = q.filter(Order.created_at >= date_from + ' 00:00:00')
    if date_to:
        q = q.filter(Order.created_at <= date_to + ' 23:59:59')
    total = q.count()
    orders = q.order_by(Order.created_at.desc()).offset((page - 1) * limit).limit(limit).all()
    mask = is_normal_user(current_user) and get_user_level(current_user) >= 4
    return jsonify({'code': 0, 'data': [o.to_dict(mask_sensitive=mask) for o in orders], 'count': total})


@app.route('/api/orders', methods=['POST'])
@login_required
def api_order_add():
    data = request.get_json() or {}
    order_no = str(data.get('order_no') or data.get('platform_no') or '').strip()
    if not order_no:
        return jsonify({'code': 0, 'msg': '请填写订单号'})
    if len(order_no) > 64:
        return jsonify({'code': 0, 'msg': '订单号不能超过64个字符'})
    if order_no_exists(order_no):
        return jsonify({'code': 0, 'msg': '订单号已存在，不能重复录入'})
    if not user_can_access_game(g.user, data.get('game_id')):
        return jsonify({'code': 0, 'msg': '无权录入该游戏订单'}), 403
    receiver_id = int(data.get('receiver_id')) if data.get('receiver_id') else None
    state = int(data.get('state', 1) or 1)
    if state == 2:
        receiver_id = None
    elif receiver_id and state in [0, 1, 2]:
        state = 3
    if receiver_id:
        receiver = User.query.get(receiver_id)
        if not receiver:
            return jsonify({'code': 0, 'msg': '接单人不存在'})
        if receiver and not user_can_access_game(receiver, data.get('game_id')):
            return jsonify({'code': 0, 'msg': '该接单人没有此游戏权限'}), 403
    order = Order(
        order_no=order_no,
        game_id=data.get('game_id'),
        area_id=data.get('area_id'),
        server_id=data.get('server_id'),
        order_type=data.get('order_type', 0),
        state=state,
        title=data.get('title', ''),
        description=data.get('description', ''),
        amount=data.get('amount', 0),
        cost=data.get('cost', 0),
        source_id=data.get('source_id'),
        creator_id=g.user.id,
        receiver_id=receiver_id,
        is_priority=data.get('is_priority', False),
        character_name=data.get('character_name', ''),
        account_info=data.get('account_info', ''),
        platform_no=data.get('platform_no') or order_no,
        received_at=datetime.now() if receiver_id else None,
        category=data.get('category', ''),
        sub_category=data.get('sub_category', ''),
        tags=data.get('tags', ''),
        is_urgent=data.get('is_urgent', False),
        pay_status='paid' if data.get('pay_status') in [1, '1', 'paid'] else 'unpaid',
        real_amount=data.get('real_amount', 0),
        remark=data.get('remark', ''),
        sales_id=data.get('sales_id'),
        tenant_id=get_tenant_id(),
    )
    db.session.add(order)
    db.session.flush()
    receiver_name = ''
    if receiver_id:
        receiver = User.query.get(receiver_id)
        receiver_name = (receiver.nickname or receiver.username) if receiver else ''
    username = g.user.nickname or g.user.username
    log_content = f'{username}将订单录入系统,订单内容：{order.title},指定接单人:{receiver_name},接单价：{order.cost}'
    log = OrderLog(order_id=order.id, user_id=g.user.id, content=log_content, tenant_id=get_tenant_id())
    db.session.add(log)
    db.session.commit()
    add_log(f'录单: {order.order_no}, 游戏={order.game_id}, 金额={order.amount}, 类型={order.order_type}', '/api/orders')
    return jsonify({'code': 1, 'msg': '录单成功', 'data': order.to_dict()})


@app.route('/api/orders/<int:oid>', methods=['PUT'])
@login_required
def api_order_edit(oid):
    order = Order.query.get_or_404(oid)
    if not check_tenant(order): return jsonify({'code': 0, 'msg': '无权操作'})
    data = request.get_json()
    if not check_order_game_access(order):
        return jsonify({'code': 0, 'msg': '无权操作该游戏订单'}), 403
    if order_readonly_for_user(order):
        return jsonify({'code': 0, 'msg': '已完成订单不可修改'})
    if 'game_id' in data and not user_can_access_game(g.user, data.get('game_id')):
        return jsonify({'code': 0, 'msg': '无权修改为该游戏'}), 403
    if 'pay_status' in data:
        ps = data['pay_status']
        data['pay_status'] = 'paid' if ps in [1, '1', 'paid'] else 'unpaid'
    username = g.user.nickname or g.user.username
    order_field_names = {'order_type':'订单类型','title':'标题','description':'描述',
        'amount':'发单价','cost':'接单价','source_id':'来源','is_priority':'优先',
        'character_name':'角色名','account_info':'账号信息','game_id':'游戏',
        'area_id':'区','server_id':'服','platform_no':'平台单号',
        'category':'分类','sub_category':'子分类','tags':'标签','is_urgent':'加急',
        'pay_status':'付款状态','real_amount':'实付金额','remark':'备注','sales_id':'销售',
        'state':'状态','receiver_id':'接单人'}
    snapshot = {}
    for k in order_field_names:
        snapshot[k] = getattr(order, k, None)
    old_amount = order.amount
    old_cost = order.cost
    old_receiver_id = order.receiver_id
    for k in ['order_type', 'title', 'description',
              'amount', 'cost', 'source_id', 'is_priority', 'character_name', 'account_info',
              'game_id', 'area_id', 'server_id',
              'platform_no', 'category', 'sub_category', 'tags', 'is_urgent', 'pay_status',
              'real_amount', 'remark', 'sales_id']:
        if k in data:
            setattr(order, k, data[k])
    if 'state' in data:
        new_state = int(data['state'])
        current_user = g.user
        is_admin = current_user.role and 'system_admin' in (json.loads(current_user.role.permissions) if current_user.role.permissions else [])
        if not is_admin:
            allowed_states = [3, 4, 5, 12]
            if new_state not in allowed_states:
                return jsonify({'code': 0, 'msg': '您没有权限修改为该状态'})
        order.state = new_state
        state_name = ORDER_STATES.get(new_state, '未知')
        log = OrderLog(order_id=oid, user_id=g.user.id, content=f'{username}将订单状态改为：{state_name}', tenant_id=get_tenant_id())
        db.session.add(log)
        if new_state == 6:
            order.finished_at = datetime.now()
    if 'receiver_id' in data:
        new_receiver_id = int(data['receiver_id']) if data['receiver_id'] else None
        receiver = User.query.get(new_receiver_id) if new_receiver_id else None
        if new_receiver_id and not receiver:
            return jsonify({'code': 0, 'msg': '接单人不存在'})
        if receiver and not user_can_access_game(receiver, data.get('game_id', order.game_id)):
            return jsonify({'code': 0, 'msg': '该接单人没有此游戏权限'}), 403
        order.receiver_id = new_receiver_id
        if order.state == 1:
            order.state = 3
        if new_receiver_id != old_receiver_id:
            order.received_at = datetime.now() if new_receiver_id else None
            receiver_name = (receiver.nickname or receiver.username) if receiver else ''
            log = OrderLog(order_id=oid, user_id=g.user.id, content=f'{username}指派订单给：{receiver_name}', tenant_id=get_tenant_id())
            db.session.add(log)
    if ('amount' in data and data['amount'] != old_amount) or ('cost' in data and data['cost'] != old_cost):
        log = OrderLog(order_id=oid, user_id=g.user.id, content=f'{username}改价：发单价 {old_amount}→{order.amount}，接单价 {old_cost}→{order.cost}', tenant_id=get_tenant_id())
        db.session.add(log)
    sync_order_bills(order)
    db.session.commit()
    changes = []
    for k in data:
        if k not in order_field_names: continue
        label = order_field_names[k]
        old_val = snapshot[k]
        new_val = getattr(order, k, None)
        if k == 'state':
            old_s = ORDER_STATES.get(old_val, old_val) if old_val is not None else '无'
            new_s = ORDER_STATES.get(new_val, new_val) if new_val is not None else '无'
            if str(old_val) != str(new_val): changes.append(f'{label}: {old_s} → {new_s}')
        elif k == 'receiver_id':
            if str(old_val) != str(new_val):
                old_rn = (User.query.get(old_val).nickname or User.query.get(old_val).username) if old_val and User.query.get(old_val) else '无'
                new_rn = (User.query.get(new_val).nickname or User.query.get(new_val).username) if new_val and User.query.get(new_val) else '无'
                changes.append(f'{label}: {old_rn} → {new_rn}')
        elif k == 'game_id':
            if str(old_val) != str(new_val):
                old_gn = Game.query.get(old_val).name if old_val and Game.query.get(old_val) else '无'
                new_gn = Game.query.get(new_val).name if new_val and Game.query.get(new_val) else '无'
                changes.append(f'{label}: {old_gn} → {new_gn}')
        elif k == 'pay_status':
            old_ps = '已付' if old_val == 'paid' else '未付'
            new_ps = '已付' if new_val == 'paid' else '未付'
            if old_ps != new_ps: changes.append(f'{label}: {old_ps} → {new_ps}')
        elif k == 'order_type':
            old_ot = ORDER_TYPES.get(old_val, old_val)
            new_ot = ORDER_TYPES.get(new_val, new_val)
            if str(old_val) != str(new_val): changes.append(f'{label}: {old_ot} → {new_ot}')
        else:
            if str(old_val) != str(new_val): changes.append(f'{label}: {old_val} → {new_val}')
    add_log(f'修改订单: {order.order_no}, {", ".join(changes) if changes else "无实际变更"}', f'/api/orders/{oid}')
    return jsonify({'code': 1, 'msg': '修改成功'})


@app.route('/api/orders/<int:oid>/receive', methods=['POST'])
@login_required
def api_order_receive(oid):
    order = Order.query.get_or_404(oid)
    if not check_tenant(order): return jsonify({'code': 0, 'msg': '无权操作'})
    if not check_order_game_access(order):
        return jsonify({'code': 0, 'msg': '无权接手该游戏订单'}), 403
    if order.state != 2:
        return jsonify({'code': 0, 'msg': '该订单不在待抢单状态'})
    order.receiver_id = g.user.id
    order.state = 3
    order.received_at = datetime.now()
    log = OrderLog(order_id=oid, user_id=g.user.id, content=f'{g.user.nickname or g.user.username}接手了订单', tenant_id=get_tenant_id())
    db.session.add(log)
    db.session.commit()
    add_log(f'接手订单: {order.order_no}, 接手人={g.user.username}', f'/api/orders/{oid}/receive')
    return jsonify({'code': 1, 'msg': '接手成功', 'data': order.to_dict()})


@app.route('/api/orders/<int:oid>/logs', methods=['GET'])
@login_required
def api_order_logs(oid):
    order = Order.query.get_or_404(oid)
    if not check_tenant(order) or not check_order_game_access(order): return jsonify({'code': 0, 'msg': '无权操作'}), 403
    logs = OrderLog.query.filter_by(order_id=oid).order_by(OrderLog.created_at.desc()).all()
    return jsonify({'code': 0, 'data': [l.to_dict() for l in logs]})


@app.route('/api/orders/<int:oid>/logs', methods=['POST'])
@login_required
def api_order_log_add(oid):
    order = Order.query.get_or_404(oid)
    if not check_tenant(order): return jsonify({'code': 0, 'msg': '无权操作'})
    if not check_order_game_access(order): return jsonify({'code': 0, 'msg': '无权操作'}), 403
    if order_readonly_for_user(order):
        return jsonify({'code': 0, 'msg': '已完成订单不可修改'})
    data = request.get_json()
    log = OrderLog(order_id=oid, user_id=g.user.id, content=data.get('content', ''), tenant_id=get_tenant_id())
    db.session.add(log)
    db.session.commit()
    return jsonify({'code': 1, 'msg': '添加成功', 'data': log.to_dict()})


@app.route('/api/orders/<int:oid>/images', methods=['POST'])
@login_required
def api_order_image_upload(oid):
    order = Order.query.get_or_404(oid)
    if not check_tenant(order): return jsonify({'code': 0, 'msg': '无权操作'})
    if not check_order_game_access(order): return jsonify({'code': 0, 'msg': '无权操作'}), 403
    if order_readonly_for_user(order):
        return jsonify({'code': 0, 'msg': '已完成订单不可修改'})
    if 'file' not in request.files:
        return jsonify({'code': 0, 'msg': '没有文件'})
    file = request.files['file']
    if file.filename == '':
        return jsonify({'code': 0, 'msg': '没有选择文件'})
    allowed_ext = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed_ext:
        return jsonify({'code': 0, 'msg': '不支持的文件类型，仅允许图片'})
    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    if size > 10 * 1024 * 1024:
        return jsonify({'code': 0, 'msg': '文件大小不能超过10MB'})
    upload_dir = os.path.join(os.path.dirname(__file__), '..', 'uploads')
    os.makedirs(upload_dir, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(upload_dir, filename)
    file.save(filepath)
    img = OrderImage(order_id=oid, filename=file.filename, filepath=filename, tenant_id=get_tenant_id())
    db.session.add(img)
    log = OrderLog(order_id=oid, user_id=g.user.id, content=f'添加图片 {img.id}', tenant_id=get_tenant_id())
    db.session.add(log)
    db.session.commit()
    return jsonify({'code': 1, 'msg': '上传成功', 'data': img.to_dict()})


@app.route('/api/orders/<int:oid>/images', methods=['GET'])
@login_required
def api_order_images(oid):
    order = Order.query.get_or_404(oid)
    if not check_tenant(order) or not check_order_game_access(order): return jsonify({'code': 0, 'msg': '无权操作'}), 403
    q = OrderImage.query.filter_by(order_id=oid)
    q = apply_tenant_filter(q, OrderImage)
    images = q.all()
    return jsonify({'code': 0, 'data': [i.to_dict() for i in images]})


@app.route('/api/order_images/<int:iid>', methods=['DELETE'])
@login_required
def api_order_image_del(iid):
    img = OrderImage.query.get_or_404(iid)
    if not check_tenant(img) or not check_order_game_access(img.order): return jsonify({'code': 0, 'msg': '无权操作'}), 403
    if order_readonly_for_user(img.order):
        return jsonify({'code': 0, 'msg': '已完成订单不可修改'})
    try:
        filepath = os.path.join(os.path.dirname(__file__), '..', 'uploads', img.filepath)
        if os.path.exists(filepath):
            os.remove(filepath)
    except:
        pass
    db.session.delete(img)
    db.session.commit()
    return jsonify({'code': 1, 'msg': '删除成功'})


@app.route('/api/orders/<int:oid>/assign', methods=['POST'])
@login_required
def api_order_assign(oid):
    order = Order.query.get_or_404(oid)
    if not check_tenant(order): return jsonify({'code': 0, 'msg': '无权操作'})
    if not check_order_game_access(order):
        return jsonify({'code': 0, 'msg': '无权指派该游戏订单'}), 403
    data = request.get_json()
    receiver_id = data.get('receiver_id')
    if not receiver_id:
        return jsonify({'code': 0, 'msg': '请选择指派人'})
    receiver_id = int(receiver_id)
    receiver = User.query.get(receiver_id)
    if not receiver:
        return jsonify({'code': 0, 'msg': '指派人不存在'})
    if receiver and not user_can_access_game(receiver, order.game_id):
        return jsonify({'code': 0, 'msg': '该接单人没有此游戏权限'}), 403
    order.receiver_id = receiver_id
    order.received_at = datetime.now()
    if order.state in [0, 1, 2]:
        order.state = 3
    log = OrderLog(order_id=oid, user_id=g.user.id, content=f'指派订单给：{receiver.nickname or receiver.username if receiver else ""}', tenant_id=get_tenant_id())
    db.session.add(log)
    db.session.commit()
    return jsonify({'code': 1, 'msg': '指派成功'})


@app.route('/api/orders/<int:oid>/change_price', methods=['POST'])
@login_required
def api_order_change_price(oid):
    order = Order.query.get_or_404(oid)
    if not check_tenant(order): return jsonify({'code': 0, 'msg': '无权操作'})
    if not check_order_game_access(order): return jsonify({'code': 0, 'msg': '无权操作该游戏订单'}), 403
    data = request.get_json()
    old_amount = order.amount
    old_cost = order.cost
    if 'amount' in data:
        order.amount = data['amount']
    if 'cost' in data:
        order.cost = data['cost']
    log = OrderLog(order_id=oid, user_id=g.user.id, content=f'改价：发单价 {old_amount}→{order.amount}，接单价 {old_cost}→{order.cost}', tenant_id=get_tenant_id())
    db.session.add(log)
    db.session.commit()
    return jsonify({'code': 1, 'msg': '改价成功'})


@app.route('/api/orders/<int:oid>/copy', methods=['POST'])
@login_required
def api_order_copy(oid):
    order = Order.query.get_or_404(oid)
    if not check_tenant(order): return jsonify({'code': 0, 'msg': '无权操作'})
    if not check_order_game_access(order): return jsonify({'code': 0, 'msg': '无权操作该游戏订单'}), 403
    new_order = Order(
        order_no=gen_order_no(),
        game_id=order.game_id,
        area_id=order.area_id,
        server_id=order.server_id,
        order_type=order.order_type,
        state=1,
        title=order.title,
        description=order.description,
        amount=order.amount,
        cost=order.cost,
        source_id=order.source_id,
        creator_id=g.user.id,
        is_priority=order.is_priority,
        character_name=order.character_name,
        account_info=order.account_info,
        platform_no=order.platform_no,
        category=order.category,
        sub_category=order.sub_category,
        tags=order.tags,
        is_urgent=order.is_urgent,
        pay_status='unpaid',
        real_amount=order.real_amount,
        remark=order.remark,
        sales_id=order.sales_id,
        tenant_id=order.tenant_id,
    )
    db.session.add(new_order)
    db.session.commit()
    log = OrderLog(order_id=new_order.id, user_id=g.user.id, content=f'从订单 {order.order_no} 复制创建', tenant_id=get_tenant_id())
    db.session.add(log)
    db.session.commit()
    return jsonify({'code': 1, 'msg': '复制成功', 'data': new_order.to_dict()})


@app.route('/api/upload', methods=['POST'])
@login_required
def api_upload():
    if 'file' not in request.files:
        return jsonify({'code': 0, 'msg': '没有文件'})
    f = request.files['file']
    if not f.filename:
        return jsonify({'code': 0, 'msg': '文件名为空'})
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']:
        return jsonify({'code': 0, 'msg': '不支持的文件类型'})
    filename = uuid.uuid4().hex + ext
    upload_dir = os.path.join(os.path.dirname(__file__), '..', 'uploads', 'qrcodes')
    os.makedirs(upload_dir, exist_ok=True)
    f.save(os.path.join(upload_dir, filename))
    url = '/uploads/qrcodes/' + filename
    return jsonify({'code': 1, 'msg': '上传成功', 'url': url})


@app.route('/uploads/<path:filename>')
@login_required
def uploaded_file(filename):
    from flask import send_from_directory
    upload_dir = os.path.join(os.path.dirname(__file__), '..', 'uploads')
    return send_from_directory(upload_dir, filename)


@app.route('/api/orders/<int:oid>/finish', methods=['POST'])
@login_required
def api_order_finish(oid):
    order = Order.query.get_or_404(oid)
    if not check_tenant(order): return jsonify({'code': 0, 'msg': '无权操作'})
    if not check_order_game_access(order): return jsonify({'code': 0, 'msg': '无权操作该游戏订单'}), 403
    if order.state != 4:
        return jsonify({'code': 0, 'msg': '该订单不在代练中状态'})
    order.state = 5
    db.session.commit()
    add_log(f'提交验收: {order.order_no}, 状态={order.state}', f'/api/orders/{oid}/finish')
    return jsonify({'code': 1, 'msg': '提交验收成功'})


@app.route('/api/bills', methods=['GET'])
@login_required
def api_bills():
    sync_completed_order_bills()
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 10, type=int)
    bill_type = request.args.get('bill_type', '')
    state = request.args.get('state', '')
    keyword = request.args.get('keyword', '')
    order_state = request.args.get('order_state', '')
    game_id = request.args.get('game_id', '')
    source_id = request.args.get('source_id', '')
    receiver_id = request.args.get('receiver_id', '')
    creator_id = request.args.get('creator_id', '')
    pay_status = request.args.get('pay_status', '')
    order_type = request.args.get('order_type', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    q = Bill.query
    q = apply_tenant_filter(q, Bill)
    q = q.filter(Bill.order_id.isnot(None), Bill.order.has())

    current_user = g.user
    view_all_bills = can_view_all_bills(current_user)
    if is_normal_user(current_user) and not view_all_bills:
        tree_ids = get_user_tree_ids(current_user.id)
        q = q.filter(Bill.user_id.in_(tree_ids))
    allowed_games = None if view_all_bills else get_user_game_ids(current_user)

    if bill_type:
        q = q.filter_by(bill_type=bill_type)
    if state:
        q = q.filter_by(state=state)
    needs_order = any([keyword, order_state, game_id, source_id, receiver_id, creator_id, pay_status, order_type, date_from, date_to]) or allowed_games is not None
    if needs_order:
        q = q.join(Bill.order, isouter=True)
    if allowed_games is not None:
        q = q.filter(Order.game_id.in_(allowed_games) if allowed_games else Order.game_id == -1)
    if keyword:
        q = q.filter(db.or_(
            Order.order_no.contains(keyword),
            Order.platform_no.contains(keyword),
            Order.character_name.contains(keyword),
            Order.title.contains(keyword),
            Order.game.has(Game.name.contains(keyword))
        ))
    if order_state != '':
        if ',' in order_state:
            q = q.filter(Order.state.in_([int(s) for s in order_state.split(',') if s != '']))
        else:
            q = q.filter(Order.state == int(order_state))
    if game_id:
        q = q.filter(Order.game_id == int(game_id))
    if source_id:
        q = q.filter(Order.source_id == int(source_id))
    if receiver_id:
        q = q.filter(Order.receiver_id == int(receiver_id))
    if creator_id:
        q = q.filter(Order.creator_id == int(creator_id))
    if pay_status:
        pay_map = {'0': 'unpaid', '1': 'paid', 'unpaid': 'unpaid', 'paid': 'paid'}
        q = q.filter(Order.pay_status == pay_map.get(pay_status, pay_status))
    if order_type != '':
        q = q.filter(Order.order_type == int(order_type))
    if date_from:
        q = q.filter(Order.created_at >= date_from + ' 00:00:00')
    if date_to:
        q = q.filter(Order.created_at <= date_to + ' 23:59:59')
    bills = q.order_by(Bill.created_at.desc()).all()
    rows = build_grouped_bill_rows(bills)
    total = len(rows)
    start = (page - 1) * limit
    page_rows = rows[start:start + limit]
    total_amount = round(float(sum((bill.amount or 0) for bill in bills)), 2)
    unsettled_amount = round(float(sum((bill.amount or 0) for bill in bills if bill.state != 'settled')), 2)
    settled_amount = round(float(sum((bill.amount or 0) for bill in bills if bill.state == 'settled')), 2)
    unsettled = len([row for row in rows if row.get('state') != 'settled'])
    settled = len([row for row in rows if row.get('state') == 'settled'])
    return jsonify({'code': 0, 'data': page_rows, 'count': total,
        'stats': {
            'total_amount': total_amount,
            'unsettled_amount': unsettled_amount,
            'settled_amount': settled_amount,
            'unsettled': unsettled,
            'settled': settled,
        }
    })


@app.route('/api/bills/<int:bid>/settle', methods=['POST'])
@login_required
def api_bill_settle(bid):
    bill = Bill.query.get_or_404(bid)
    if not check_tenant(bill): return jsonify({'code': 0, 'msg': '无权操作'})
    if bill.order_id:
        q = Bill.query.filter_by(order_id=bill.order_id)
        q = apply_tenant_filter(q, Bill)
        bills = q.all()
    else:
        bills = [bill]
    now = datetime.now()
    for item in bills:
        item.state = 'settled'
        item.settled_at = now
    db.session.commit()
    return jsonify({'code': 1, 'msg': '结算成功'})


@app.route('/api/admin_logs', methods=['GET'])
@login_required
def api_admin_logs():
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    user_id = request.args.get('user_id', '')
    keyword = request.args.get('keyword', '')
    action_type = request.args.get('action_type', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    q = AdminLog.query
    current_user = g.user
    is_sys_admin = current_user.role and 'system_admin' in (json.loads(current_user.role.permissions) if current_user.role.permissions else [])
    is_company_admin = current_user.role and 'company_admin' in (json.loads(current_user.role.permissions) if current_user.role.permissions else [])
    if is_sys_admin and not current_user.tenant_id:
        pass
    elif is_sys_admin or is_company_admin:
        q = q.filter_by(tenant_id=current_user.tenant_id)
    else:
        q = q.filter_by(user_id=current_user.id)
    if user_id:
        if not is_sys_admin and not is_company_admin:
            if int(user_id) != current_user.id:
                return jsonify({'code': 0, 'data': [], 'count': 0})
        q = q.filter_by(user_id=int(user_id))
    if keyword:
        q = q.filter(AdminLog.action.contains(keyword))
    if action_type:
        type_map = {
            '访问页面': '访问页面',
            '登录': '登录',
            '操作': ['修改', '删除', '添加', '设置', '指派', '改价', '切换'],
            '修改': ['修改', '设置', '配置', '更新'],
            '订单': ['订单', '指派', '抢单', '抛单', '撤回', '拆分', '录单', '接手'],
        }
        if action_type in type_map:
            val = type_map[action_type]
            if isinstance(val, str):
                q = q.filter(AdminLog.action.contains(val))
            else:
                q = q.filter(db.or_(*[AdminLog.action.contains(v) for v in val]))
    if date_from:
        q = q.filter(AdminLog.created_at >= date_from + ' 00:00:00')
    if date_to:
        q = q.filter(AdminLog.created_at <= date_to + ' 23:59:59')
    total = q.count()
    logs = q.order_by(AdminLog.created_at.desc()).offset((page - 1) * limit).limit(limit).all()
    return jsonify({'code': 0, 'data': [l.to_dict() for l in logs], 'count': total})


@app.route('/api/orders/ranking', methods=['GET'])
@login_required
def api_order_ranking():
    month = request.args.get('month', datetime.now().strftime('%Y-%m'))
    q = Order.query.filter(Order.receiver_id != None)
    q = apply_tenant_filter(q, Order)
    if month:
        q = q.filter(db.func.strftime('%Y-%m', Order.created_at) == month)
    current_user = g.user
    if is_normal_user(current_user):
        tree_ids = get_user_tree_ids(current_user.id)
        q = q.filter(Order.receiver_id.in_(tree_ids))
    
    receivers = db.session.query(
        Order.receiver_id,
        db.func.count(Order.id).label('total'),
        db.func.sum(db.case((Order.state == 6, 1), else_=0)).label('finished'),
        db.func.coalesce(db.func.sum(Order.cost), 0).label('total_cost'),
    ).filter(Order.receiver_id != None).group_by(Order.receiver_id)
    
    if month:
        receivers = receivers.filter(db.func.strftime('%Y-%m', Order.created_at) == month)
    
    from sqlalchemy import cast, Integer
    results = []
    for r in receivers.all():
        user = User.query.get(r.receiver_id)
        if not user:
            continue
        finished = int(r.finished or 0)
        total = int(r.total or 0)
        results.append({
            'receiver_id': r.receiver_id,
            'receiver_name': user.nickname or user.username,
            'total': total,
            'finished': finished,
            'finish_rate': round(finished / total * 100, 1) if total > 0 else 0,
            'total_cost': round(float(r.total_cost or 0), 2),
        })
    results.sort(key=lambda x: x['total'], reverse=True)
    for i, r in enumerate(results):
        r['rank'] = i + 1
    return jsonify({'code': 0, 'data': results})


@app.route('/api/orders/stats', methods=['GET'])
@login_required
def api_order_stats():
    start = request.args.get('start', '')
    end = request.args.get('end', '')
    q = Order.query
    q = apply_tenant_filter(q, Order)
    current_user = g.user
    q = apply_user_game_filter(q, current_user, Order)
    if get_user_level(current_user) >= 4:
        tree_ids = get_user_tree_ids(current_user.id)
        q = q.filter(db.or_(Order.creator_id.in_(tree_ids), Order.receiver_id.in_(tree_ids)))
    if start:
        q = q.filter(Order.created_at >= start)
    if end:
        q = q.filter(Order.created_at <= end + ' 23:59:59')
    
    total = q.count()
    finished = q.filter(Order.state == 6).count()
    doing = q.filter(Order.state.in_([3, 4, 5])).count()
    pending = q.filter(Order.state.in_([0, 1, 2])).count()
    order_ids = [o.id for o in q.with_entities(Order.id).all()]
    total_amount = db.session.query(db.func.sum(Order.amount)).filter(Order.id.in_(order_ids)).scalar() or 0
    total_cost = db.session.query(db.func.sum(Order.cost)).filter(Order.id.in_(order_ids)).scalar() or 0
    
    result = {
        'total': total,
        'finished': finished,
        'doing': doing,
        'pending': pending,
    }
    if not (is_normal_user(current_user) and get_user_level(current_user) >= 4):
        result['total_amount'] = round(float(total_amount), 2)
        result['total_cost'] = round(float(total_cost), 2)
        result['profit'] = round(float(total_amount) - float(total_cost), 2)
    
    return jsonify({
        'code': 1,
        'data': result
    })


@app.route('/api/order_logs', methods=['GET'])
@login_required
def api_order_logs_global():
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 15, type=int)
    keyword = request.args.get('keyword', '')
    order_no = request.args.get('order_no', '')
    
    q = OrderLog.query
    q = apply_tenant_filter(q, OrderLog)
    current_user = g.user
    if is_normal_user(current_user):
        tree_ids = get_user_tree_ids(current_user.id)
        order_ids = Order.query.filter(db.or_(Order.creator_id.in_(tree_ids), Order.receiver_id.in_(tree_ids))).with_entities(Order.id)
        q = q.filter(OrderLog.order_id.in_(order_ids))
    
    if keyword:
        q = q.filter(OrderLog.content.contains(keyword))
    if order_no:
        q = q.join(OrderLog.order).filter(Order.order_no.contains(order_no))
    
    total = q.count()
    logs = q.order_by(OrderLog.created_at.desc()).offset((page - 1) * limit).limit(limit).all()
    return jsonify({'code': 0, 'data': [l.to_dict() for l in logs], 'count': total})


@app.route('/api/orders/batch', methods=['POST'])
@admin_required
def api_order_batch():
    data = request.get_json()
    action = data.get('action', '')
    ids = data.get('ids', [])
    if not ids:
        return jsonify({'code': 0, 'msg': '请选择订单'})
    orders = Order.query.filter(Order.id.in_(ids)).all()
    if any((not check_tenant(order)) or (not check_order_game_access(order)) for order in orders):
        return jsonify({'code': 0, 'msg': '无权操作所选订单'}), 403
    username = g.user.nickname or g.user.username
    if action == 'assign':
        receiver_id = data.get('receiver_id')
        if not receiver_id:
            return jsonify({'code': 0, 'msg': '请选择指派人'})
        receiver_id = int(receiver_id)
        receiver = User.query.get(receiver_id)
        if not receiver:
            return jsonify({'code': 0, 'msg': '指派人不存在'})
        if any(not user_can_access_game(receiver, order.game_id) for order in orders):
            return jsonify({'code': 0, 'msg': '该接单人没有所选订单的游戏权限'}), 403
        count = 0
        for order in orders:
            order.receiver_id = receiver_id
            order.received_at = datetime.now()
            if order.state in [0, 1, 2]:
                order.state = 3
            log = OrderLog(order_id=order.id, user_id=g.user.id, content=f'{username}批量指派给：{receiver.nickname or receiver.username}', tenant_id=order.tenant_id)
            db.session.add(log)
            count += 1
        db.session.commit()
        return jsonify({'code': 1, 'msg': f'成功指派{count}个订单'})
    elif action == 'change_price':
        amount = data.get('amount')
        cost = data.get('cost')
        count = 0
        for order in orders:
            if amount is not None:
                order.amount = amount
            if cost is not None:
                order.cost = cost
            log = OrderLog(order_id=order.id, user_id=g.user.id, content=f'{username}批量改价：发单价→{order.amount}，接单价→{order.cost}', tenant_id=order.tenant_id)
            db.session.add(log)
            count += 1
        db.session.commit()
        return jsonify({'code': 1, 'msg': f'成功改价{count}个订单'})
    elif action == 'cancel':
        count = 0
        for order in orders:
            if order.state not in [6, 23, 24]:
                order.state = 23
                log = OrderLog(order_id=order.id, user_id=g.user.id, content=f'{username}批量撤销订单', tenant_id=order.tenant_id)
                db.session.add(log)
                count += 1
        db.session.commit()
        return jsonify({'code': 1, 'msg': f'成功撤销{count}个订单'})
    elif action == 'change_state':
        new_state = data.get('state')
        if new_state is None:
            return jsonify({'code': 0, 'msg': '请选择状态'})
        state_name = ORDER_STATES.get(new_state, '未知')
        count = 0
        for order in orders:
            order.state = new_state
            if new_state == 6:
                order.finished_at = datetime.now()
                sync_order_bills(order)
            log = OrderLog(order_id=order.id, user_id=g.user.id, content=f'{username}批量修改状态为：{state_name}', tenant_id=order.tenant_id)
            db.session.add(log)
            count += 1
        db.session.commit()
        return jsonify({'code': 1, 'msg': f'成功修改{count}个订单状态'})
    elif action == 'pay':
        count = 0
        for order in orders:
            order.pay_status = 'paid'
            log = OrderLog(order_id=order.id, user_id=g.user.id, content=f'{username}批量标记已收款', tenant_id=order.tenant_id)
            db.session.add(log)
            count += 1
        db.session.commit()
        return jsonify({'code': 1, 'msg': f'成功标记{count}个订单已收款'})
    elif action == 'throw':
        count = 0
        for order in orders:
            if order.state in [1, 3, 4]:
                old_receiver = (order.receiver.nickname or order.receiver.username) if order.receiver else ''
                order.receiver_id = None
                order.received_at = None
                order.state = 2
                log = OrderLog(order_id=order.id, user_id=g.user.id, content=f'{username}批量抛单，原接单人：{old_receiver}', tenant_id=order.tenant_id)
                db.session.add(log)
                count += 1
        db.session.commit()
        return jsonify({'code': 1, 'msg': f'成功抛单{count}个订单'})
    elif action == 'recall':
        count = 0
        for order in orders:
            if order.state in [2, 3]:
                old_state = ORDER_STATES.get(order.state, '未知')
                order.state = 1
                order.receiver_id = None
                order.received_at = None
                log = OrderLog(order_id=order.id, user_id=g.user.id, content=f'{username}批量撤回，原状态：{old_state}', tenant_id=order.tenant_id)
                db.session.add(log)
                count += 1
        db.session.commit()
        return jsonify({'code': 1, 'msg': f'成功撤回{count}个订单'})
    else:
        return jsonify({'code': 0, 'msg': '未知操作'})


@app.route('/api/orders/export', methods=['GET'])
@login_required
def api_order_export():
    import csv as csv_mod
    import io as io_mod
    q = Order.query
    q = apply_tenant_filter(q, Order)
    current_user = g.user
    if get_user_level(current_user) >= 4:
        tree_ids = get_user_tree_ids(current_user.id)
        q = q.filter(db.or_(Order.creator_id.in_(tree_ids), Order.receiver_id.in_(tree_ids)))
    q = apply_user_game_filter(q, current_user, Order)
    state = request.args.get('state', '')
    keyword = request.args.get('keyword', '')
    game_id = request.args.get('game_id', '')
    pay_status = request.args.get('pay_status', '')
    order_type = request.args.get('order_type', '')
    source_id = request.args.get('source_id', '')
    if state != '':
        q = q.filter_by(state=int(state))
    if keyword:
        q = q.filter((Order.order_no.contains(keyword)) | (Order.character_name.contains(keyword)) | (Order.title.contains(keyword)))
    if game_id:
        q = q.filter_by(game_id=int(game_id))
    if pay_status:
        pay_map = {'0': 'unpaid', '1': 'paid', 'unpaid': 'unpaid', 'paid': 'paid'}
        q = q.filter_by(pay_status=pay_map.get(pay_status, pay_status))
    if order_type != '':
        q = q.filter_by(order_type=int(order_type))
    if source_id:
        q = q.filter_by(source_id=int(source_id))
    ids_param = request.args.get('ids', '')
    if ids_param:
        id_list = [int(x) for x in ids_param.split(',') if x.strip().isdigit()]
        if id_list:
            q = q.filter(Order.id.in_(id_list))
    orders = q.order_by(Order.created_at.desc()).limit(5000).all()
    export_type = request.args.get('type', 'csv')
    from flask import make_response
    if export_type == 'order_nos':
        output = io_mod.StringIO()
        for o in orders:
            output.write(o.order_no + '\n')
        output.seek(0)
        response = make_response(output.getvalue().encode('utf-8'))
        response.headers['Content-Type'] = 'text/plain; charset=utf-8'
        response.headers['Content-Disposition'] = 'attachment; filename=order_nos.txt'
        return response
    elif export_type == 'xlsx':
        try:
            import openpyxl
        except ImportError:
            return jsonify({'code': 0, 'msg': '服务器未安装openpyxl，无法导出Excel'})
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = '订单导出'
        headers = ['订单号', '平台单号', '代练内容', '角色名', '游戏', '区服', '状态', '发单价', '接单价', '实收', '收款状态', '来源', '创建人', '接单人', '销售客服', '是否加急', '标签', '重要备注', '创建时间']
        ws.append(headers)
        for o in orders:
            ws.append([
                o.order_no, o.platform_no, o.title, o.character_name,
                o.game.name if o.game else '',
                (o.area.name if o.area else '') + ' ' + (o.server.name if o.server else ''),
                ORDER_STATES.get(o.state, '未知'),
                o.amount, o.cost, o.real_amount,
                {'unpaid': '未收款', 'paid': '已收款'}.get(o.pay_status, '未知'),
                o.source.name if o.source else '',
                o.creator.nickname or o.creator.username if o.creator else '',
                o.receiver.nickname or o.receiver.username if o.receiver else '',
                o.sales.nickname or o.sales.username if o.sales else '',
                '是' if o.is_urgent else '否',
                o.tags, o.remark,
                o.created_at.strftime('%Y-%m-%d %H:%M:%S') if o.created_at else '',
            ])
        xlsx_io = io_mod.BytesIO()
        wb.save(xlsx_io)
        xlsx_io.seek(0)
        response = make_response(xlsx_io.getvalue())
        response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        response.headers['Content-Disposition'] = 'attachment; filename=orders_export.xlsx'
        return response
    else:
        output = io_mod.StringIO()
        writer = csv_mod.writer(output)
        writer.writerow(['订单号', '平台单号', '代练内容', '角色名', '游戏', '区服', '状态', '发单价', '接单价', '实收', '收款状态', '来源', '创建人', '接单人', '销售客服', '是否加急', '标签', '重要备注', '创建时间'])
        for o in orders:
            writer.writerow([
                o.order_no, o.platform_no, o.title, o.character_name,
                o.game.name if o.game else '',
                (o.area.name if o.area else '') + ' ' + (o.server.name if o.server else ''),
                ORDER_STATES.get(o.state, '未知'),
                o.amount, o.cost, o.real_amount,
                {'unpaid': '未收款', 'paid': '已收款'}.get(o.pay_status, '未知'),
                o.source.name if o.source else '',
                o.creator.nickname or o.creator.username if o.creator else '',
                o.receiver.nickname or o.receiver.username if o.receiver else '',
                o.sales.nickname or o.sales.username if o.sales else '',
                '是' if o.is_urgent else '否',
                o.tags, o.remark,
                o.created_at.strftime('%Y-%m-%d %H:%M:%S') if o.created_at else '',
            ])
        output.seek(0)
        content = '\ufeff' + output.getvalue()
        response = make_response(content.encode('utf-8'))
        response.headers['Content-Type'] = 'text/csv; charset=utf-8'
        response.headers['Content-Disposition'] = 'attachment; filename=orders_export.csv'
        return response


@app.route('/api/profile/update', methods=['POST'])
@login_required
def api_profile_update():
    user = g.user
    data = request.get_json()
    if 'nickname' in data:
        user.nickname = data['nickname']
    if 'avatar' in data:
        user.avatar = data['avatar']
    if 'old_password' in data and data['old_password']:
        if not user.check_password(data['old_password']):
            return jsonify({'code': 0, 'msg': '原密码错误'})
        if 'new_password' in data and data['new_password']:
            user.set_password(data['new_password'])
    db.session.commit()
    return jsonify({'code': 1, 'msg': '修改成功'})


@app.route('/api/profile/avatar', methods=['POST'])
@login_required
def api_profile_avatar():
    if 'file' not in request.files:
        return jsonify({'code': 0, 'msg': '没有文件'})
    file = request.files['file']
    if file.filename == '':
        return jsonify({'code': 0, 'msg': '没有选择文件'})
    allowed_ext = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed_ext:
        return jsonify({'code': 0, 'msg': '不支持的文件类型'})
    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    if size > 5 * 1024 * 1024:
        return jsonify({'code': 0, 'msg': '文件大小不能超过5MB'})
    upload_dir = os.path.join(os.path.dirname(__file__), '..', 'uploads', 'avatars')
    os.makedirs(upload_dir, exist_ok=True)
    ext = os.path.splitext(file.filename)[1]
    filename = f"{g.user.id}_{uuid.uuid4().hex[:8]}{ext}"
    filepath = os.path.join(upload_dir, filename)
    file.save(filepath)
    g.user.avatar = f'/uploads/avatars/{filename}'
    db.session.commit()
    return jsonify({'code': 1, 'msg': '上传成功', 'data': {'avatar': g.user.avatar}})


@app.route('/api/orders/<int:oid>/detail', methods=['GET'])
@login_required
def api_order_detail(oid):
    order = Order.query.get_or_404(oid)
    if not check_tenant(order): return jsonify({'code': 0, 'msg': '无权操作'})
    current_user = g.user
    if not check_order_game_access(order, current_user): return jsonify({'code': 0, 'msg': '无权查看该游戏订单'}), 403
    if get_user_level(current_user) >= 4:
        tree_ids = get_user_tree_ids(current_user.id)
        if order.creator_id not in tree_ids and order.receiver_id not in tree_ids:
            return jsonify({'code': 0, 'msg': '无权查看'}), 403
    mask = is_normal_user(current_user) and get_user_level(current_user) >= 4
    result = order.to_dict(mask_sensitive=mask)
    result['logs'] = [l.to_dict() for l in order.logs]
    result['images'] = [i.to_dict() for i in order.images]
    return jsonify({'code': 1, 'data': result})


@app.route('/api/orders/by_no/<order_no>', methods=['GET'])
@login_required
def api_order_detail_by_no(order_no):
    order = Order.query.filter_by(order_no=order_no).first()
    if not order: return jsonify({'code': 0, 'msg': '订单不存在'})
    if not check_tenant(order): return jsonify({'code': 0, 'msg': '无权操作'})
    current_user = g.user
    if not check_order_game_access(order, current_user): return jsonify({'code': 0, 'msg': '无权查看该游戏订单'}), 403
    if get_user_level(current_user) >= 4:
        tree_ids = get_user_tree_ids(current_user.id)
        if order.creator_id not in tree_ids and order.receiver_id not in tree_ids:
            return jsonify({'code': 0, 'msg': '无权查看'}), 403
    mask = is_normal_user(current_user) and get_user_level(current_user) >= 4
    result = order.to_dict(mask_sensitive=mask)
    result['logs'] = [l.to_dict() for l in order.logs]
    result['images'] = [i.to_dict() for i in order.images]
    return jsonify({'code': 1, 'data': result})


@app.route('/api/orders/<int:oid>/toggle_pay', methods=['POST'])
@login_required
def api_order_toggle_pay(oid):
    order = Order.query.get_or_404(oid)
    if not check_tenant(order): return jsonify({'code': 0, 'msg': '无权操作'})
    if not check_order_game_access(order): return jsonify({'code': 0, 'msg': '无权操作该游戏订单'}), 403
    order.pay_status = 'paid' if order.pay_status == 'unpaid' else 'unpaid'
    username = g.user.nickname or g.user.username
    pay_name = '已收款' if order.pay_status == 'paid' else '未收款'
    log = OrderLog(order_id=oid, user_id=g.user.id, content=f'{username}切换收款状态为：{pay_name}', tenant_id=order.tenant_id)
    db.session.add(log)
    db.session.commit()
    return jsonify({'code': 1, 'msg': '操作成功', 'data': {'pay_status': order.pay_status}})


@app.route('/api/orders/<int:oid>/throw', methods=['POST'])
@login_required
def api_order_throw(oid):
    order = Order.query.get_or_404(oid)
    if not check_tenant(order): return jsonify({'code': 0, 'msg': '无权操作'})
    if not check_order_game_access(order): return jsonify({'code': 0, 'msg': '无权操作该游戏订单'}), 403
    if order.state not in [1, 3, 4]:
        return jsonify({'code': 0, 'msg': '当前状态不可抛单'})
    old_receiver = order.receiver.nickname or order.receiver.username if order.receiver else ''
    order.receiver_id = None
    order.received_at = None
    order.state = 2
    username = g.user.nickname or g.user.username
    log = OrderLog(order_id=oid, user_id=g.user.id, content=f'{username}抛单，原接单人：{old_receiver}', tenant_id=order.tenant_id)
    db.session.add(log)
    db.session.commit()
    return jsonify({'code': 1, 'msg': '抛单成功'})


@app.route('/api/orders/<int:oid>/split', methods=['POST'])
@admin_required
def api_order_split(oid):
    order = Order.query.get_or_404(oid)
    if not check_tenant(order): return jsonify({'code': 0, 'msg': '无权操作'})
    if not check_order_game_access(order): return jsonify({'code': 0, 'msg': '无权操作该游戏订单'}), 403
    base_order_no = display_order_no(order)
    if not base_order_no:
        return jsonify({'code': 0, 'msg': '原订单号为空，不能拆分'})
    if base_order_no.startswith('拆'):
        return jsonify({'code': 0, 'msg': '拆分订单不能再次拆分'})
    new_order_no = '拆' + base_order_no
    if len(new_order_no) > 64:
        return jsonify({'code': 0, 'msg': '拆分后的订单号过长'})
    if Order.query.filter_by(parent_order_id=order.id).first() or order_no_exists(new_order_no):
        return jsonify({'code': 0, 'msg': '该订单号已经拆分过，不能重复拆分'})
    data = request.get_json()
    split_amount = data.get('amount', 0)
    if not split_amount or float(split_amount) <= 0:
        return jsonify({'code': 0, 'msg': '拆分金额必须大于0'})
    if float(split_amount) >= float(order.amount or 0):
        return jsonify({'code': 0, 'msg': '拆分金额必须小于原订单金额'})
    new_order = Order(
        order_no=new_order_no,
        game_id=order.game_id, area_id=order.area_id, server_id=order.server_id,
        order_type=order.order_type, state=1, title=order.title,
        description=order.description, amount=float(split_amount),
        cost=round(float(order.cost or 0) * float(split_amount) / float(order.amount or 1), 2),
        source_id=order.source_id, creator_id=g.user.id,
        is_priority=order.is_priority, character_name=order.character_name,
        account_info=order.account_info, platform_no=new_order_no,
        category=order.category, sub_category=order.sub_category, tags=order.tags,
        is_urgent=order.is_urgent, pay_status=order.pay_status,
        remark=data.get('remark', '拆分自 ' + order.order_no), sales_id=order.sales_id,
        tenant_id=order.tenant_id, parent_order_id=order.id,
    )
    order.amount = round(float(order.amount or 0) - float(split_amount), 2)
    order.cost = round(float(order.cost or 0) - float(new_order.cost or 0), 2)
    db.session.add(new_order)
    db.session.flush()
    username = g.user.nickname or g.user.username
    log1 = OrderLog(order_id=order.id, user_id=g.user.id, content=f'{username}拆分订单，拆出{new_order.order_no}，金额{split_amount}', tenant_id=order.tenant_id)
    log2 = OrderLog(order_id=new_order.id, user_id=g.user.id, content=f'由订单{order.order_no}拆分创建', tenant_id=order.tenant_id)
    db.session.add(log1)
    db.session.add(log2)
    db.session.commit()
    add_log(f'拆分订单: {order.order_no} → {new_order.order_no}, 拆分金额={split_amount}')
    return jsonify({'code': 1, 'msg': '拆分成功', 'data': new_order.to_dict()})


@app.route('/api/orders/<int:oid>/recall', methods=['POST'])
@admin_required
def api_order_recall(oid):
    order = Order.query.get_or_404(oid)
    if not check_tenant(order): return jsonify({'code': 0, 'msg': '无权操作'})
    if not check_order_game_access(order): return jsonify({'code': 0, 'msg': '无权操作该游戏订单'}), 403
    if order.state not in [2, 3]:
        return jsonify({'code': 0, 'msg': '当前状态不可撤回'})
    old_state = ORDER_STATES.get(order.state, '未知')
    old_receiver = (order.receiver.nickname or order.receiver.username) if order.receiver else ''
    order.state = 1
    order.receiver_id = None
    order.received_at = None
    username = g.user.nickname or g.user.username
    log = OrderLog(order_id=oid, user_id=g.user.id, content=f'{username}撤回订单，原状态：{old_state}，原接单人：{old_receiver or "无"}', tenant_id=order.tenant_id)
    db.session.add(log)
    db.session.commit()
    add_log(f'撤回订单: {order.order_no}, {old_state} → 待分配')
    return jsonify({'code': 1, 'msg': '撤回成功'})
@login_required
def api_order_cancel(oid):
    order = Order.query.get_or_404(oid)
    if not check_tenant(order): return jsonify({'code': 0, 'msg': '无权操作'})
    if not check_order_game_access(order): return jsonify({'code': 0, 'msg': '无权操作该游戏订单'}), 403
    if order.state in [6, 13]:
        return jsonify({'code': 0, 'msg': '当前状态不可撤单'})
    order.state = 13
    username = g.user.nickname or g.user.username
    log = OrderLog(order_id=oid, user_id=g.user.id, content=f'{username}撤单', tenant_id=order.tenant_id)
    db.session.add(log)
    db.session.commit()
    return jsonify({'code': 1, 'msg': '撤单成功'})


@app.route('/api/orders/<int:oid>/pause', methods=['POST'])
@login_required
def api_order_pause(oid):
    order = Order.query.get_or_404(oid)
    if not check_tenant(order): return jsonify({'code': 0, 'msg': '无权操作'})
    if not check_order_game_access(order): return jsonify({'code': 0, 'msg': '无权操作该游戏订单'}), 403
    if order.state not in [3, 4]:
        return jsonify({'code': 0, 'msg': '当前状态不可暂停'})
    old_state = order.state
    order.state = 10
    username = g.user.nickname or g.user.username
    log = OrderLog(order_id=oid, user_id=g.user.id, content=f'{username}暂停订单（原状态：{old_state}）', tenant_id=order.tenant_id)
    db.session.add(log)
    db.session.commit()
    return jsonify({'code': 1, 'msg': '已暂停'})


@app.route('/api/orders/<int:oid>/resume', methods=['POST'])
@login_required
def api_order_resume(oid):
    order = Order.query.get_or_404(oid)
    if not check_tenant(order): return jsonify({'code': 0, 'msg': '无权操作'})
    if not check_order_game_access(order): return jsonify({'code': 0, 'msg': '无权操作该游戏订单'}), 403
    if order.state != 10:
        return jsonify({'code': 0, 'msg': '当前状态不可恢复'})
    order.state = 4
    username = g.user.nickname or g.user.username
    log = OrderLog(order_id=oid, user_id=g.user.id, content=f'{username}恢复订单为代练中', tenant_id=order.tenant_id)
    db.session.add(log)
    db.session.commit()
    return jsonify({'code': 1, 'msg': '已恢复'})


@app.route('/api/orders/<int:oid>/accept', methods=['POST'])
@login_required
def api_order_accept(oid):
    order = Order.query.get_or_404(oid)
    if not check_tenant(order): return jsonify({'code': 0, 'msg': '无权操作'})
    if not check_order_game_access(order): return jsonify({'code': 0, 'msg': '无权操作该游戏订单'}), 403
    if order.state != 5:
        return jsonify({'code': 0, 'msg': '当前状态不可验收'})
    order.state = 6
    order.finished_at = datetime.now()
    sync_order_bills(order)
    username = g.user.nickname or g.user.username
    log = OrderLog(order_id=oid, user_id=g.user.id, content=f'{username}验收通过，订单完成', tenant_id=order.tenant_id)
    db.session.add(log)
    db.session.commit()
    return jsonify({'code': 1, 'msg': '验收完成'})


@app.route('/api/orders/<int:oid>/abnormal', methods=['POST'])
@login_required
def api_order_abnormal(oid):
    order = Order.query.get_or_404(oid)
    if not check_tenant(order): return jsonify({'code': 0, 'msg': '无权操作'})
    if not check_order_game_access(order): return jsonify({'code': 0, 'msg': '无权操作该游戏订单'}), 403
    if order.state == 11:
        return jsonify({'code': 0, 'msg': '订单已是异常状态'})
    old_state = order.state
    order.state = 11
    username = g.user.nickname or g.user.username
    log = OrderLog(order_id=oid, user_id=g.user.id, content=f'{username}标记异常（原状态：{old_state}）', tenant_id=order.tenant_id)
    db.session.add(log)
    db.session.commit()
    return jsonify({'code': 1, 'msg': '已标记异常'})


@app.route('/api/orders/<int:oid>/problem', methods=['POST'])
@login_required
def api_order_problem(oid):
    order = Order.query.get_or_404(oid)
    if not check_tenant(order): return jsonify({'code': 0, 'msg': '无权操作'})
    if not check_order_game_access(order): return jsonify({'code': 0, 'msg': '无权操作该游戏订单'}), 403
    if order.state == 12:
        return jsonify({'code': 0, 'msg': '订单已是问题单'})
    old_state = order.state
    order.state = 12
    username = g.user.nickname or g.user.username
    log = OrderLog(order_id=oid, user_id=g.user.id, content=f'{username}标记为问题单（原状态：{old_state}）', tenant_id=order.tenant_id)
    db.session.add(log)
    db.session.commit()
    return jsonify({'code': 1, 'msg': '已标记问题单'})


@app.route('/api/clear_cache', methods=['POST'])
@admin_required
def api_clear_cache():
    db.session.expire_all()
    add_log('清除系统缓存', '/api/clear_cache')
    return jsonify({'code': 1, 'msg': '缓存已清除'})


@app.route('/api/backup_db', methods=['POST'])
@admin_required
def api_backup_db():
    import shutil
    db_path = os.path.join(os.path.dirname(__file__), '..', 'data.db')
    if not os.path.exists(db_path):
        return jsonify({'code': 0, 'msg': '数据库文件不存在'})
    backup_dir = os.path.join(os.path.dirname(__file__), '..', 'backups')
    os.makedirs(backup_dir, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = os.path.join(backup_dir, f'data_{ts}.db')
    shutil.copy2(db_path, backup_path)
    add_log(f'备份数据库: {backup_path}', '/api/backup_db')
    return jsonify({'code': 1, 'msg': '备份成功', 'data': {'path': backup_path}})


@app.route('/api/orders/<int:oid>', methods=['DELETE'])
@admin_required
def api_order_delete(oid):
    order = Order.query.get_or_404(oid)
    if not check_tenant(order): return jsonify({'code': 0, 'msg': '无权操作'})
    if not check_order_game_access(order): return jsonify({'code': 0, 'msg': '无权操作该游戏订单'}), 403
    OrderLog.query.filter_by(order_id=oid).delete()
    OrderImage.query.filter_by(order_id=oid).delete()
    Bill.query.filter_by(order_id=oid).delete()
    db.session.delete(order)
    db.session.commit()
    add_log(f'删除订单: {order.order_no}', f'/api/orders/{oid}')
    return jsonify({'code': 1, 'msg': '删除成功'})


@app.route('/api/brand', methods=['GET'])
def api_brand():
    tenant = get_current_tenant()
    if tenant:
        return jsonify({'code': 1, 'data': {
            'company_name': tenant.company_name or tenant.prefix,
            'logo': tenant.logo or '',
            'prefix': tenant.prefix,
            'is_tenant': True
        }})
    return jsonify({'code': 1, 'data': {
        'company_name': '订单管理系统',
        'logo': '',
        'prefix': '',
        'is_tenant': False
    }})


@app.route('/api/check_status', methods=['GET'])
@login_required
def api_check_status():
    return jsonify({'code': 1, 'msg': 'ok'})


@app.route('/api/dashboard/stats', methods=['GET'])
@login_required
def api_dashboard_stats():
    current_user = g.user
    is_agent = get_user_level(current_user) >= 4
    if is_agent:
        tree_ids = get_user_tree_ids(current_user.id)
        oq = Order.query.filter(db.or_(Order.creator_id.in_(tree_ids), Order.receiver_id.in_(tree_ids)))
        oq = apply_tenant_filter(oq, Order)
        oq = apply_user_game_filter(oq, current_user, Order)
        total_orders = oq.count()
        pending = oq.filter(Order.state.in_([1, 2, 3])).count()
        doing = oq.filter_by(state=4).count()
        finished = oq.filter_by(state=6).count()
        total_users = User.query.filter(User.id.in_(tree_ids)).count()
        total_agents = User.query.filter(User.id.in_(tree_ids), User.is_agent == True).count()
    else:
        oq = apply_tenant_filter(Order.query, Order)
        oq = apply_user_game_filter(oq, current_user, Order)
        total_orders = oq.count()
        pending = oq.filter(Order.state.in_([1, 2, 3])).count()
        doing = oq.filter_by(state=4).count()
        finished = oq.filter_by(state=6).count()
        uq = apply_tenant_filter(User.query, User)
        total_users = uq.count()
        total_agents = uq.filter_by(is_agent=True).count()
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


@app.route('/api/tenants', methods=['GET'])
@admin_required
def api_tenants():
    tenants = Tenant.query.order_by(Tenant.created_at.desc()).all()
    return jsonify({'code': 0, 'data': [t.to_dict() for t in tenants], 'count': len(tenants)})


@app.route('/api/tenants', methods=['POST'])
@admin_required
def api_tenant_add():
    data = request.get_json()
    prefix = data.get('prefix', '').strip().lower()
    if not prefix:
        return jsonify({'code': 0, 'msg': '子域名前缀不能为空'})
    if Tenant.query.filter_by(prefix=prefix).first():
        return jsonify({'code': 0, 'msg': '该前缀已存在'})

    tenant = Tenant(
        prefix=prefix,
        company_name=data.get('company_name', ''),
        logo=data.get('logo', ''),
        contact_name=data.get('contact_name', ''),
        contact_phone=data.get('contact_phone', ''),
        domain=f"{prefix}.{data.get('base_domain', 'cr.com')}",
        status=data.get('status', 'normal'),
        max_users=data.get('max_users', 10),
        max_orders=data.get('max_orders', 1000),
    )
    db.session.add(tenant)
    db.session.flush()

    admin_role = Role(
        name='系统管理员',
        desc='租户管理员',
        permissions='["system_admin"]',
        tenant_id=tenant.id,
    )
    db.session.add(admin_role)
    db.session.flush()

    admin_user = User(
        username=data.get('admin_username', prefix + '_admin'),
        nickname=data.get('admin_nickname', tenant.company_name + '管理员'),
        role_id=admin_role.id,
        status='normal',
        tenant_id=tenant.id,
    )
    admin_user.set_password(data.get('admin_password', '123456'))
    db.session.add(admin_user)

    db.session.commit()
    add_log(f'新增租户: {tenant.company_name}({tenant.prefix})', '/api/tenants')
    return jsonify({'code': 1, 'msg': '创建成功', 'data': tenant.to_dict()})


@app.route('/api/tenants/<int:tid>', methods=['PUT'])
@admin_required
def api_tenant_edit(tid):
    tenant = Tenant.query.get_or_404(tid)
    data = request.get_json()
    for k in ['company_name', 'logo', 'contact_name', 'contact_phone', 'status', 'max_users', 'max_orders']:
        if k in data:
            setattr(tenant, k, data[k])
    db.session.commit()
    return jsonify({'code': 1, 'msg': '修改成功'})


@app.route('/api/tenants/<int:tid>', methods=['DELETE'])
@admin_required
def api_tenant_del(tid):
    tenant = Tenant.query.get_or_404(tid)
    for order in Order.query.filter_by(tenant_id=tid).all():
        OrderLog.query.filter_by(order_id=order.id).delete()
        OrderImage.query.filter_by(order_id=order.id).delete()
        Bill.query.filter_by(order_id=order.id).delete()
    Order.query.filter_by(tenant_id=tid).delete()
    Bill.query.filter_by(tenant_id=tid).delete()
    Source.query.filter_by(tenant_id=tid).delete()
    Role.query.filter_by(tenant_id=tid).delete()
    AdminLog.query.filter_by(tenant_id=tid).delete()
    User.query.filter_by(tenant_id=tid).delete()
    Game.query.filter_by(tenant_id=tid).delete()
    db.session.delete(tenant)
    db.session.commit()
    add_log(f'删除租户: {tenant.company_name}', f'/api/tenants/{tid}')
    return jsonify({'code': 1, 'msg': '删除成功'})


@app.route('/api/tenants/current', methods=['GET'])
@login_required
def api_tenant_current():
    tenant = get_current_tenant()
    if tenant:
        return jsonify({'code': 1, 'data': tenant.to_dict()})
    return jsonify({'code': 1, 'data': None})


@app.route('/api/tenant_bindings', methods=['GET'])
@login_required
def api_tenant_bindings():
    tid = get_tenant_id()
    if tid is None:
        return jsonify({'code': 0, 'msg': '仅租户可使用绑定上家功能'})
    bindings = TenantBinding.query.filter(
        db.or_(TenantBinding.parent_tenant_id == tid, TenantBinding.child_tenant_id == tid)
    ).order_by(TenantBinding.created_at.desc()).all()
    return jsonify({'code': 0, 'data': [b.to_dict() for b in bindings]})


@app.route('/api/tenant_bindings/apply', methods=['POST'])
@login_required
def api_tenant_binding_apply():
    tid = get_tenant_id()
    if tid is None:
        return jsonify({'code': 0, 'msg': '仅租户可使用绑定上家功能'})
    data = request.get_json()
    parent_prefix = data.get('parent_prefix', '').strip()
    if not parent_prefix:
        return jsonify({'code': 0, 'msg': '请输入上家标识'})
    parent = Tenant.query.filter_by(prefix=parent_prefix, status='normal').first()
    if not parent:
        return jsonify({'code': 0, 'msg': '未找到该上家，请确认标识是否正确'})
    if parent.id == tid:
        return jsonify({'code': 0, 'msg': '不能绑定自己'})
    existing = TenantBinding.query.filter_by(parent_tenant_id=parent.id, child_tenant_id=tid).first()
    if existing:
        return jsonify({'code': 0, 'msg': '已存在绑定关系（状态：' + existing.status + '）'})
    binding = TenantBinding(parent_tenant_id=parent.id, child_tenant_id=tid, status='pending')
    db.session.add(binding)
    db.session.commit()
    add_log(f'申请绑定上家: {parent.company_name}', '/api/tenant_bindings/apply')
    return jsonify({'code': 1, 'msg': '申请已发送，等待上家确认'})


@app.route('/api/tenant_bindings/<int:bid>/confirm', methods=['POST'])
@login_required
def api_tenant_binding_confirm(bid):
    tid = get_tenant_id()
    binding = TenantBinding.query.get_or_404(bid)
    if binding.parent_tenant_id != tid:
        return jsonify({'code': 0, 'msg': '无权操作'})
    binding.status = 'active'
    db.session.commit()
    add_log(f'确认绑定下家: {binding.child_tenant.company_name}', f'/api/tenant_bindings/{bid}/confirm')
    return jsonify({'code': 1, 'msg': '已确认绑定'})


@app.route('/api/tenant_bindings/<int:bid>/reject', methods=['POST'])
@login_required
def api_tenant_binding_reject(bid):
    tid = get_tenant_id()
    binding = TenantBinding.query.get_or_404(bid)
    if binding.parent_tenant_id != tid:
        return jsonify({'code': 0, 'msg': '无权操作'})
    binding.status = 'rejected'
    db.session.commit()
    return jsonify({'code': 1, 'msg': '已拒绝'})


@app.route('/api/tenant_bindings/<int:bid>', methods=['DELETE'])
@login_required
def api_tenant_binding_del(bid):
    tid = get_tenant_id()
    binding = TenantBinding.query.get_or_404(bid)
    if binding.parent_tenant_id != tid and binding.child_tenant_id != tid:
        return jsonify({'code': 0, 'msg': '无权操作'})
    db.session.delete(binding)
    db.session.commit()
    return jsonify({'code': 1, 'msg': '已解除绑定'})


@app.route('/api/tenant_bindings/dispatch', methods=['POST'])
@login_required
def api_tenant_binding_dispatch():
    tid = get_tenant_id()
    if tid is None:
        return jsonify({'code': 0, 'msg': '仅租户可使用派单功能'})
    data = request.get_json()
    order_id = data.get('order_id')
    target_tenant_id = data.get('target_tenant_id')
    if not order_id or not target_tenant_id:
        return jsonify({'code': 0, 'msg': '参数不完整'})
    order = Order.query.get_or_404(order_id)
    if not check_tenant(order):
        return jsonify({'code': 0, 'msg': '无权操作该订单'})
    binding = TenantBinding.query.filter_by(parent_tenant_id=tid, child_tenant_id=target_tenant_id, status='active').first()
    if not binding:
        return jsonify({'code': 0, 'msg': '未与目标租户建立绑定关系'})
    new_no = 'TB' + datetime.now().strftime('%Y%m%d%H%M%S') + str(uuid.uuid4().int)[:4]
    new_order = Order(
        order_no=new_no,
        game_id=order.game_id,
        area_id=order.area_id,
        server_id=order.server_id,
        order_type=order.order_type,
        state=1,
        title=order.title,
        description=order.description,
        amount=data.get('amount', order.cost or 0),
        cost=0,
        character_name=order.character_name,
        account_info=order.account_info,
        platform_no=order.order_no,
        category=order.category,
        sub_category=order.sub_category,
        tags=order.tags,
        is_urgent=order.is_urgent,
        pay_status='unpaid',
        remark='来自上家派单：' + (order.order_no or ''),
        tenant_id=target_tenant_id,
        parent_order_id=order.id,
        from_tenant_id=tid,
    )
    db.session.add(new_order)
    order.state = 4
    log = OrderLog(order_id=order.id, user_id=g.user.id, content=f'{g.user.nickname or g.user.username}将订单派发给下家：{binding.child_tenant.company_name}', tenant_id=tid)
    db.session.add(log)
    log2 = OrderLog(order_id=new_order.id, user_id=g.user.id, content=f'收到上家派单，来源：{binding.parent_tenant.company_name}，原单号：{order.order_no}', tenant_id=target_tenant_id)
    db.session.add(log2)
    db.session.commit()
    add_log(f'派单到下家: {binding.child_tenant.company_name}', f'/api/tenant_bindings/dispatch')
    return jsonify({'code': 1, 'msg': '派单成功'})


@app.route('/api/tenant_bindings/children', methods=['GET'])
@login_required
def api_tenant_binding_children():
    tid = get_tenant_id()
    if tid is None:
        return jsonify({'code': 0, 'data': []})
    bindings = TenantBinding.query.filter_by(parent_tenant_id=tid, status='active').all()
    return jsonify({'code': 0, 'data': [{'id': b.child_tenant_id, 'company_name': b.child_tenant.company_name, 'prefix': b.child_tenant.prefix} for b in bindings]})


def init_db():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        admin_role = Role(name='系统管理员', desc='拥有所有权限', permissions='["system_admin"]', level=1)
        db.session.add(admin_role)
        db.session.flush()

        agent_role = Role(name='公司管理员', desc='管理公司内部事务和所有订单', permissions='["dashboard","general_profile","auth_role","auth_admin","auth_adminlog","company_source","game_manage","order_paidan","order_qiangdan","order_all","order_add","order_ranking","order_stats","order_logs","finance_bill","platform_settings","company_info","tenant_binding"]', level=2)
        db.session.add(agent_role)
        db.session.flush()

        cs_role = Role(name='客服', desc='处理客户问题和订单', permissions='["dashboard","general_profile","order_all","order_add","order_paidan","order_qiangdan","order_stats","order_logs"]', level=3)
        db.session.add(cs_role)
        db.session.flush()

        player_role = Role(name='打手', desc='接单代练', permissions='["dashboard","general_profile","order_qiangdan","order_paidan","order_stats","order_logs"]', level=4)
        db.session.add(player_role)
        db.session.flush()

        finance_role = Role(name='财务', desc='财务结算', permissions='["dashboard","general_profile","finance_bill"]', level=3)
        db.session.add(finance_role)
        db.session.flush()

        admin = User(username='admin', nickname='系统管理员', role_id=admin_role.id, status='normal')
        admin.set_password('admin123')
        db.session.add(admin)

        admin2 = User(username='admin2', nickname='管理员2号', role_id=admin_role.id, status='normal')
        admin2.set_password('admin2123')
        db.session.add(admin2)

        agent2 = User(username='agent2', nickname='代理2号', role_id=agent_role.id, status='normal', is_agent=True, agent_level=1)
        agent2.set_password('agent2')
        db.session.add(agent2)

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
        print('数据库初始化完成！默认账号: admin / admin123, admin2 / admin2123')


def upgrade_roles():
    role_updates = {
        '系统管理员': {'permissions': '["system_admin"]', 'level': 1},
        '代理': {'permissions': '["dashboard","general_profile","auth_role","auth_admin","auth_adminlog","company_source","game_manage","order_paidan","order_qiangdan","order_all","order_add","order_ranking","order_stats","order_logs","finance_bill","platform_settings","company_info","tenant_binding"]', 'level': 2, 'name': '公司管理员'},
        '公司管理员': {'permissions': '["dashboard","general_profile","auth_role","auth_admin","auth_adminlog","company_source","game_manage","order_paidan","order_qiangdan","order_all","order_add","order_ranking","order_stats","order_logs","finance_bill","platform_settings","company_info","tenant_binding"]', 'level': 2},
        '客服': {'permissions': '["dashboard","general_profile","order_all","order_add","order_paidan","order_qiangdan","order_stats","order_logs"]', 'level': 3},
        '打手': {'permissions': '["dashboard","general_profile","order_qiangdan","order_paidan","order_stats","order_logs"]', 'level': 4},
        '财务': {'permissions': '["dashboard","general_profile","finance_bill"]', 'level': 3},
    }
    for role in Role.query.all():
        if role.name in role_updates:
            upd = role_updates[role.name]
            role.permissions = upd['permissions']
            role.level = upd['level']
            if 'name' in upd:
                role.name = upd['name']
    db.session.commit()
    print('角色权限升级完成！')


def quote_sqlite_identifier(name):
    return '"' + name.replace('"', '""') + '"'


def ensure_model_columns(models):
    added = []
    dialect = db.engine.dialect
    for model in models:
        table_name = model.__tablename__
        table_sql = quote_sqlite_identifier(table_name)
        existing = {row[1] for row in db.session.execute(text(f'PRAGMA table_info({table_sql})')).fetchall()}
        for column in model.__table__.columns:
            if column.primary_key or column.name in existing:
                continue
            col_sql = quote_sqlite_identifier(column.name)
            col_type = column.type.compile(dialect=dialect)
            db.session.execute(text(f'ALTER TABLE {table_sql} ADD COLUMN {col_sql} {col_type}'))
            added.append(f'{table_name}.{column.name}')
    if added:
        db.session.commit()
        print('数据库结构升级完成：' + ', '.join(added))


def ensure_schema():
    db.create_all()
    try:
        ensure_model_columns([
            User, LoginToken, Role, Order, OrderLog, Tenant, OrderImage, Game,
            GameArea, GameServer, Source, AdminLog, Bill, PlatformSetting,
            TenantBinding,
        ])
    except Exception as exc:
        db.session.rollback()
        print(f'数据库结构检查失败：{exc}')


with app.app_context():
    ensure_schema()


if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
