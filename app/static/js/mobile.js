(function () {
    var mq = window.matchMedia('(max-width: 768px)');

    function isMobile() {
        return mq.matches;
    }

    function authedUrl(url) {
        var token = sessionStorage.getItem('auth_token') || '';
        if (!token || url.indexOf('token=') > -1) return url;
        return url + (url.indexOf('?') > -1 ? '&' : '?') + 'token=' + encodeURIComponent(token);
    }

    function mobileSafeBack(fallbackUrl) {
        var target = authedUrl(fallbackUrl || '/');
        try {
            if (window.parent && window.parent !== window && window.parent.layui && window.parent.layui.layer) {
                var frameIndex = window.parent.layui.layer.getFrameIndex(window.name);
                if (frameIndex !== undefined) {
                    window.parent.layui.layer.close(frameIndex);
                    return;
                }
            }
        } catch (err) {}

        if (window.top && window.top !== window) {
            window.top.location.href = target;
        } else {
            window.location.replace(target);
        }
    }

    window.mobileSafeBack = mobileSafeBack;

    function closeSidebar() {
        document.body.classList.remove('mobile-sidebar-open');
    }

    function ensureSidebarMask() {
        if (!document.querySelector('.main-sidebar')) return;
        if (document.querySelector('.mobile-sidebar-mask')) return;

        var mask = document.createElement('div');
        mask.className = 'mobile-sidebar-mask';
        mask.addEventListener('click', closeSidebar);
        document.body.appendChild(mask);
    }

    function bindShell() {
        ensureSidebarMask();

        var toggle = document.getElementById('sidebarToggle');
        if (toggle && !toggle.dataset.mobileBound) {
            toggle.dataset.mobileBound = '1';
            toggle.addEventListener('click', function (event) {
                if (!isMobile()) return;
                event.preventDefault();
                event.stopPropagation();
                document.body.classList.toggle('mobile-sidebar-open');
            }, true);
        }

        document.addEventListener('click', function (event) {
            if (!isMobile()) return;
            var target = event.target;
            if (target.closest && target.closest('.sidebar-menu a[data-url]')) {
                setTimeout(closeSidebar, 120);
            }
        });
    }

    function fitLayers() {
        if (!isMobile()) return;

        var viewportH = window.innerHeight || document.documentElement.clientHeight || 640;
        document.querySelectorAll('.layui-layer').forEach(function (layer) {
            layer.style.left = '8px';
            layer.style.right = '8px';
            layer.style.width = 'auto';
            layer.style.maxWidth = 'none';

            var height = layer.offsetHeight || 0;
            var top = Math.max(8, Math.round((viewportH - Math.min(height, viewportH - 16)) / 2));
            layer.style.top = top + 'px';

            var content = layer.querySelector('.layui-layer-content');
            if (content) {
                content.style.maxHeight = Math.max(220, viewportH - 130) + 'px';
                content.style.overflow = 'auto';
            }
        });
    }

    function patchLayuiLayer() {
        if (!window.layui || !layui.layer || layui.layer.__mobilePatched) return;

        var layer = layui.layer;
        var open = layer.open;
        layer.open = function (options) {
            options = options || {};
            if (isMobile()) {
                options.area = ['calc(100vw - 16px)', options.type === 2 ? 'calc(100vh - 96px)' : 'auto'];
                options.offset = 'auto';
                var success = options.success;
                var end = options.end;
                options.success = function () {
                    fitLayers();
                    if (typeof success === 'function') {
                        success.apply(this, arguments);
                    }
                    setTimeout(fitLayers, 60);
                };
                options.end = function () {
                    if (typeof end === 'function') {
                        end.apply(this, arguments);
                    }
                    setTimeout(fitLayers, 20);
                };
            }
            var index = open.call(layer, options);
            setTimeout(fitLayers, 30);
            return index;
        };
        layui.layer.__mobilePatched = true;
    }

    function patchLayuiTable() {
        if (!window.layui || !layui.table || layui.table.__mobilePatched) return;

        var table = layui.table;
        var render = table.render;
        table.render = function (options) {
            options = options || {};
            if (isMobile()) {
                options.height = options.height || 'full-112';
                options.limit = options.limit || 10;
            }
            var instance = render.call(table, options);
            setTimeout(fitLayers, 30);
            return instance;
        };
        layui.table.__mobilePatched = true;
    }

    function patchLayui() {
        patchLayuiLayer();
        patchLayuiTable();
    }

    function init() {
        bindShell();
        patchLayui();
        fitLayers();

        var tries = 0;
        var timer = setInterval(function () {
            patchLayui();
            tries += 1;
            if (tries > 30 || (window.layui && layui.layer && layui.table)) {
                clearInterval(timer);
            }
        }, 100);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    window.addEventListener('resize', function () {
        if (!isMobile()) {
            closeSidebar();
        }
        fitLayers();
    });

    window.addEventListener('orientationchange', function () {
        setTimeout(fitLayers, 180);
    });
})();
