import sys
import hashlib
import os
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'app'))
from app import db, app, User, Role, Tenant

def list_roles():
    with app.app_context():
        for r in Role.query.filter_by(tenant_id=None).order_by(Role.id).all():
            print(f"{r.id}|{r.name}")

def create_user(username, password, nickname, role_name, is_agent, tenant_id=None):
    with app.app_context():
        if User.query.filter_by(username=username, tenant_id=tenant_id).first():
            print(f"ERROR: 用户名 '{username}' 已存在")
            return False
        q = Role.query.filter_by(name=role_name)
        if tenant_id is not None:
            q = q.filter_by(tenant_id=tenant_id)
        else:
            q = q.filter_by(tenant_id=None)
        role = q.first()
        if not role:
            print(f"ERROR: 角色 '{role_name}' 不存在")
            return False
        user = User(
            username=username,
            nickname=nickname or username,
            role_id=role.id,
            status='normal',
            is_agent=bool(int(is_agent)),
            agent_level=1 if int(is_agent) else 0,
            tenant_id=tenant_id
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        tenant_info = f'（租户ID: {tenant_id}）' if tenant_id else '（主站）'
        print(f"OK: 账号创建成功 - {username}（角色：{role_name}，代理：{'是' if int(is_agent) else '否'}）{tenant_info}")
        return True

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--list-roles':
        list_roles()
    elif len(sys.argv) >= 5:
        username = sys.argv[1]
        password = sys.argv[2]
        role_name = sys.argv[3]
        is_agent = sys.argv[4]
        nickname = sys.argv[5] if len(sys.argv) > 5 else username
        tenant_id = int(sys.argv[6]) if len(sys.argv) > 6 else None
        if not create_user(username, password, nickname, role_name, is_agent, tenant_id):
            sys.exit(1)
    else:
        print("USAGE: python create_user.py --list-roles")
        print("       python create_user.py <username> <password> <role_name> <is_agent> [nickname] [tenant_id]")
        sys.exit(1)
