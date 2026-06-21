import os, sys
os.chdir(r'G:\gutaipan\易语言\易语言源码区\自己用的还有个动态图工具\DingDanGuanLi')
sys.path.insert(0, r'G:\gutaipan\易语言\易语言源码区\自己用的还有个动态图工具\DingDanGuanLi')
try:
    from app.app import app
    print('App imported OK')
    print('Template folder:', app.template_folder)
    print('Static folder:', app.static_folder)
    with app.app_context():
        from app.app import db
        db.create_all()
        print('DB OK')
except Exception as e:
    print('Error:', e)
    import traceback
    traceback.print_exc()