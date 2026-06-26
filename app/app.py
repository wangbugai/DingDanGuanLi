import os
import hashlib
import functools
import uuid
import json
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, g
from flask_sqlalchemy import SQLAlchemy
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
            'is_agent': self.is_agent,
            'agent_level': self.agent_level,
            'parent_id': self.parent_id,
            'status': self.status,
            'tenant_id': self.tenant_id,
            'tenant_name': self.tenant.company_name if self.tenant else '主站',
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
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

    tenant = db.relationship('Tenant', backref='roles')

    def to_dict(self):

        return {
            'id': self.id,
            'name': self.name,
            'desc': self.desc,
            'permissions': json.loads(self.permissions) if self.permissions else [],
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
            'source_id': self.source_id,
            'source_name': self.source.name if self.source else (Tenant.query.get(self.from_tenant_id).company_name if self.from_tenant_id and Tenant.query.get(self.from_tenant_id) else ''),
            'creator_name': self.creator.nickname or self.creator.username if self.creator else '',
            'receiver_id': self.receiver_id,
            'receiver_name': self.receiver.nickname or self.receiver.username if self.receiver else '',
            'is_priority': self.is_priority,
            'character_name': self.character_name,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else '',
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S') if self.updated_at else '',
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
        return {
            'id': self.id,
            'order_id': self.order_id,
            'filename': self.filename,
            'filepath': self.filepath,
            'url': '/uploads/' + self.filepath if self.filepath else '',
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

    parent_tenant = db.relationship('Tenant', foreign_keys='TenantBinding.parent_tenant_id', backref=db.backref('child_bindings', overlaps='parent_bindings'))
    child_tenant = db.relationship('Tenant', foreign_keys='TenantBinding.child_tenant_id', backref=db.backref('parent_bindings', overlaps='child_bindings'))

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
    add_log('保存平台设置', '/api/platform_settings')
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
    q = User.query
    q = apply_tenant_filter(q, User)

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
    db.session.add(user)
    db.session.commit()
    add_log(f'新增用户: {user.username}', '/api/users')
    return jsonify({'code': 1, 'msg': '添加成功'})


@app.route('/api/users/<int:uid>', methods=['PUT'])
@admin_required
def api_user_edit(uid):
    user = User.query.get_or_404(uid)
    if not check_tenant(user): return jsonify({'code': 0, 'msg': '无权操作'})
    data = request.get_json()
    current_user = g.user
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
    if not check_tenant(user): return jsonify({'code': 0, 'msg': '无权操作'})
    cascade_delete(uid)
    db.session.delete(user)
    db.session.commit()
    add_log(f'删除用户: {user.username}', f'/api/users/{uid}')
    return jsonify({'code': 1, 'msg': '删除成功'})


@app.route('/api/users/<int:uid>/set_agent', methods=['POST'])
@admin_required
def api_user_set_agent(uid):
    user = User.query.get_or_404(uid)
    if not check_tenant(user): return jsonify({'code': 0, 'msg': '无权操作'})
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
    source.name = data.get('name', source.name)
    source.desc = data.get('desc', source.desc)
    db.session.commit()
    return jsonify({'code': 1, 'msg': '修改成功'})


@app.route('/api/sources/<int:sid>', methods=['DELETE'])
@login_required
def api_source_del(sid):
    source = Source.query.get_or_404(sid)
    if not check_tenant(source): return jsonify({'code': 0, 'msg': '无权操作'})
    db.session.delete(source)
    db.session.commit()
    return jsonify({'code': 1, 'msg': '删除成功'})


# ============ 游戏管理API ============

@app.route('/api/games', methods=['GET'])
@login_required
def api_games():
    games = apply_tenant_filter(Game.query, Game).order_by(Game.sort, Game.id).all()
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
    if not check_tenant(game): return jsonify({'code': 0, 'msg': '无权操作'})
    db.session.delete(game)
    db.session.commit()
    return jsonify({'code': 1, 'msg': '删除成功'})


@app.route('/api/games/<int:gid>/areas', methods=['GET'])
@login_required
def api_game_areas(gid):
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
    if is_normal_user(current_user):
        tree_ids = get_user_tree_ids(current_user.id)
        q = q.filter(db.or_(Order.creator_id.in_(tree_ids), Order.receiver_id.in_(tree_ids)))

    if state != '':
        if ',' in state:
            q = q.filter(Order.state.in_([int(s) for s in state.split(',')]))
        else:
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
    return jsonify({'code': 0, 'data': [o.to_dict() for o in orders], 'count': total})


@app.route('/api/orders', methods=['POST'])
@login_required
def api_order_add():
    data = request.get_json()
    receiver_id = data.get('receiver_id')
    state = data.get('state', 1)
    if receiver_id and state in [0, 1, 2]:
        state = 3
    order = Order(
        order_no=gen_order_no(),
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
        platform_no=data.get('platform_no', ''),
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
    add_log(f'录单: {order.order_no}', '/api/orders')
    return jsonify({'code': 1, 'msg': '录单成功', 'data': order.to_dict()})


@app.route('/api/orders/<int:oid>', methods=['PUT'])
@login_required
def api_order_edit(oid):
    order = Order.query.get_or_404(oid)
    if not check_tenant(order): return jsonify({'code': 0, 'msg': '无权操作'})
    data = request.get_json()
    if 'pay_status' in data:
        ps = data['pay_status']
        data['pay_status'] = 'paid' if ps in [1, '1', 'paid'] else 'unpaid'
    username = g.user.nickname or g.user.username
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
        order.state = new_state
        state_name = ORDER_STATES.get(new_state, '未知')
        log = OrderLog(order_id=oid, user_id=g.user.id, content=f'{username}将订单状态改为：{state_name}', tenant_id=get_tenant_id())
        db.session.add(log)
        if new_state == 6:
            order.finished_at = datetime.now()
            if order.receiver_id and not Bill.query.filter_by(order_id=order.id, user_id=order.receiver_id).first():
                bill = Bill(order_id=order.id, user_id=order.receiver_id, bill_type='player', amount=order.cost or 0, state='unpaid', tenant_id=order.tenant_id)
                db.session.add(bill)
            if order.creator_id and order.creator_id != order.receiver_id and not Bill.query.filter_by(order_id=order.id, user_id=order.creator_id).first():
                bill2 = Bill(order_id=order.id, user_id=order.creator_id, bill_type='service', amount=(order.amount or 0) - (order.cost or 0), state='unpaid', tenant_id=order.tenant_id)
                db.session.add(bill2)
    if 'receiver_id' in data:
        order.receiver_id = data['receiver_id']
        if order.state == 1:
            order.state = 3
        if data['receiver_id'] != old_receiver_id:
            receiver = User.query.get(data['receiver_id'])
            receiver_name = (receiver.nickname or receiver.username) if receiver else ''
            log = OrderLog(order_id=oid, user_id=g.user.id, content=f'{username}指派订单给：{receiver_name}', tenant_id=get_tenant_id())
            db.session.add(log)
    if ('amount' in data and data['amount'] != old_amount) or ('cost' in data and data['cost'] != old_cost):
        log = OrderLog(order_id=oid, user_id=g.user.id, content=f'{username}改价：发单价 {old_amount}→{order.amount}，接单价 {old_cost}→{order.cost}', tenant_id=get_tenant_id())
        db.session.add(log)
    db.session.commit()
    add_log(f'修改订单: {order.order_no}', f'/api/orders/{oid}')
    return jsonify({'code': 1, 'msg': '修改成功'})


@app.route('/api/orders/<int:oid>/receive', methods=['POST'])
@login_required
def api_order_receive(oid):
    order = Order.query.get_or_404(oid)
    if not check_tenant(order): return jsonify({'code': 0, 'msg': '无权操作'})
    if order.state != 2:
        return jsonify({'code': 0, 'msg': '该订单不在待抢单状态'})
    order.receiver_id = g.user.id
    order.state = 3
    log = OrderLog(order_id=oid, user_id=g.user.id, content=f'{g.user.nickname or g.user.username}接手了订单', tenant_id=get_tenant_id())
    db.session.add(log)
    db.session.commit()
    add_log(f'接手订单: {order.order_no}', f'/api/orders/{oid}/receive')
    return jsonify({'code': 1, 'msg': '接手成功'})


@app.route('/api/orders/<int:oid>/logs', methods=['GET'])
@login_required
def api_order_logs(oid):
    logs = OrderLog.query.filter_by(order_id=oid).order_by(OrderLog.created_at.desc()).all()
    return jsonify({'code': 0, 'data': [l.to_dict() for l in logs]})


@app.route('/api/orders/<int:oid>/logs', methods=['POST'])
@login_required
def api_order_log_add(oid):
    order = Order.query.get_or_404(oid)
    if not check_tenant(order): return jsonify({'code': 0, 'msg': '无权操作'})
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
    q = OrderImage.query.filter_by(order_id=oid)
    q = apply_tenant_filter(q, OrderImage)
    images = q.all()
    return jsonify({'code': 0, 'data': [i.to_dict() for i in images]})


@app.route('/api/order_images/<int:iid>', methods=['DELETE'])
@login_required
def api_order_image_del(iid):
    img = OrderImage.query.get_or_404(iid)
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
    data = request.get_json()
    receiver_id = data.get('receiver_id')
    if not receiver_id:
        return jsonify({'code': 0, 'msg': '请选择指派人'})
    receiver = User.query.get(receiver_id)
    order.receiver_id = receiver_id
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
    q = apply_tenant_filter(q, Bill)

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
    return jsonify({'code': 0, 'data': [b.to_dict() for b in bills], 'count': total,
        'stats': {
            'total_amount': round(float(db.session.query(db.func.sum(Bill.amount)).filter(Bill.id.in_([b.id for b in bills])).scalar() or 0), 2),
            'unsettled': q.filter(Bill.state == 'unpaid').count(),
            'settled': q.filter(Bill.state == 'settled').count(),
        }
    })


@app.route('/api/bills/<int:bid>/settle', methods=['POST'])
@login_required
def api_bill_settle(bid):
    bill = Bill.query.get_or_404(bid)
    if not check_tenant(bill): return jsonify({'code': 0, 'msg': '无权操作'})
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
    q = apply_tenant_filter(q, AdminLog)
    current_user = g.user
    if is_normal_user(current_user):
        tree_ids = get_user_tree_ids(current_user.id)
        q = q.filter(AdminLog.user_id.in_(tree_ids))
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
    if is_normal_user(current_user):
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
    
    return jsonify({
        'code': 1,
        'data': {
            'total': total,
            'finished': finished,
            'doing': doing,
            'pending': pending,
            'total_amount': round(float(total_amount), 2),
            'total_cost': round(float(total_cost), 2),
            'profit': round(float(total_amount) - float(total_cost), 2),
        }
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
        q = q.filter(OrderLog.user_id.in_(tree_ids))
    
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
    username = g.user.nickname or g.user.username
    if action == 'assign':
        receiver_id = data.get('receiver_id')
        if not receiver_id:
            return jsonify({'code': 0, 'msg': '请选择指派人'})
        receiver = User.query.get(receiver_id)
        count = 0
        for order in orders:
            order.receiver_id = receiver_id
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
    if is_normal_user(current_user):
        tree_ids = get_user_tree_ids(current_user.id)
        q = q.filter(db.or_(Order.creator_id.in_(tree_ids), Order.receiver_id.in_(tree_ids)))
    state = request.args.get('state', '')
    keyword = request.args.get('keyword', '')
    game_id = request.args.get('game_id', '')
    pay_status = request.args.get('pay_status', '')
    if state != '':
        q = q.filter_by(state=int(state))
    if keyword:
        q = q.filter((Order.order_no.contains(keyword)) | (Order.character_name.contains(keyword)) | (Order.title.contains(keyword)))
    if game_id:
        q = q.filter_by(game_id=int(game_id))
    if pay_status:
        pay_map = {'0': 'unpaid', '1': 'paid', 'unpaid': 'unpaid', 'paid': 'paid'}
        q = q.filter_by(pay_status=pay_map.get(pay_status, pay_status))
    ids_param = request.args.get('ids', '')
    if ids_param:
        id_list = [int(x) for x in ids_param.split(',') if x.strip().isdigit()]
        if id_list:
            q = q.filter(Order.id.in_(id_list))
    orders = q.order_by(Order.created_at.desc()).limit(5000).all()
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
    from flask import make_response
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
    if is_normal_user(current_user):
        tree_ids = get_user_tree_ids(current_user.id)
        if order.creator_id not in tree_ids and order.receiver_id not in tree_ids:
            return jsonify({'code': 0, 'msg': '无权查看'}), 403
    result = order.to_dict()
    result['logs'] = [l.to_dict() for l in order.logs]
    result['images'] = [i.to_dict() for i in order.images]
    return jsonify({'code': 1, 'data': result})


@app.route('/api/orders/<int:oid>/toggle_pay', methods=['POST'])
@login_required
def api_order_toggle_pay(oid):
    order = Order.query.get_or_404(oid)
    if not check_tenant(order): return jsonify({'code': 0, 'msg': '无权操作'})
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
    if order.state not in [3, 4]:
        return jsonify({'code': 0, 'msg': '当前状态不可抛单'})
    old_receiver = order.receiver.nickname or order.receiver.username if order.receiver else ''
    order.receiver_id = None
    order.state = 2
    username = g.user.nickname or g.user.username
    log = OrderLog(order_id=oid, user_id=g.user.id, content=f'{username}抛单，原接单人：{old_receiver}', tenant_id=order.tenant_id)
    db.session.add(log)
    db.session.commit()
    return jsonify({'code': 1, 'msg': '抛单成功'})


@app.route('/api/orders/<int:oid>/cancel', methods=['POST'])
@login_required
def api_order_cancel(oid):
    order = Order.query.get_or_404(oid)
    if not check_tenant(order): return jsonify({'code': 0, 'msg': '无权操作'})
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
    if order.state != 5:
        return jsonify({'code': 0, 'msg': '当前状态不可验收'})
    order.state = 6
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
    OrderLog.query.filter_by(order_id=oid).delete()
    OrderImage.query.filter_by(order_id=oid).delete()
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
    is_agent = is_normal_user(current_user)
    if is_agent:
        tree_ids = get_user_tree_ids(current_user.id)
        oq = Order.query.filter(db.or_(Order.creator_id.in_(tree_ids), Order.receiver_id.in_(tree_ids)))
        oq = apply_tenant_filter(oq, Order)
        total_orders = oq.count()
        pending = oq.filter(Order.state.in_([1, 2, 3])).count()
        doing = oq.filter_by(state=4).count()
        finished = oq.filter_by(state=6).count()
        total_users = User.query.filter(User.id.in_(tree_ids)).count()
        total_agents = User.query.filter(User.id.in_(tree_ids), User.is_agent == True).count()
    else:
        oq = apply_tenant_filter(Order.query, Order)
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
        admin_role = Role(name='系统管理员', desc='拥有所有权限', permissions='["system_admin"]')
        db.session.add(admin_role)
        db.session.flush()

        agent_role = Role(name='代理', desc='代理角色，可发展下级', permissions='["dashboard","general_profile","company_role","company_user","company_source","game_manage","order_paidan","order_qiangdan","order_all","order_add","order_ranking","order_stats","order_logs","finance_bill","platform_settings","company_info","tenant_binding"]')
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
        print('数据库初始化完成！默认账号: admin / admin123')


if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
