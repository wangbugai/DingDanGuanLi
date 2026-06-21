import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.app import app, init_db

if __name__ == '__main__':
    with app.app_context():
        init_db()
    print('=' * 50)
    print('  订单管理系统已启动！')
    print('  访问地址: http://127.0.0.1:5000')
    print('  默认账号: admin / admin123')
    print('=' * 50)
    app.run(host='0.0.0.0', port=5000, debug=False)
