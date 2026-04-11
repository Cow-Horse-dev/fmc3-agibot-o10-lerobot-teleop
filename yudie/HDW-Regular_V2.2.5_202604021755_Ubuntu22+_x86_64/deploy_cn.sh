#!/bin/sh

#############################################
# HandDriver Web 部署脚本
# 用途：在 Ubuntu 系统上部署服务端和网页客户端
#############################################

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # 无颜色

# 默认配置
DEFAULT_PORT=8088
DEFAULT_DEPLOY_DIR="/var/www/handdriver"
DEFAULT_WS_PORT=7789
DEFAULT_SERVER_DIR=""
RUN_AFTER_DEPLOY=false
QUICK_DEPLOY=false

# 输出函数
print_info() {
    printf '%b\n' "${GREEN}[信息]${NC} $1"
}

print_warn() {
    printf '%b\n' "${YELLOW}[警告]${NC} $1"
}

print_error() {
    printf '%b\n' "${RED}[错误]${NC} $1"
}

# 显示帮助信息
show_help() {
    cat << EOF
${BLUE}HandDriver Web 部署脚本${NC}

${YELLOW}用法:${NC}
    sudo ./deploy_cn.sh [选项]

${YELLOW}选项:${NC}
    -m, --mode MODE           部署模式: all(全部), server(仅服务端), client(仅客户端) (默认: all)
    -s, --server-ip IP        服务器 IP 地址 (客户端部署时必填)
    -p, --port PORT           Nginx 监听端口 (默认: $DEFAULT_PORT)
    -d, --deploy-dir DIR      网页客户端部署目录 (默认: $DEFAULT_DEPLOY_DIR)
    --server-dir DIR          HDService 目录路径
    -r, --run                 部署完成后运行服务器并打开浏览器
    -y, --yes                 跳过所有确认提示
    -h, --help                显示此帮助信息

${YELLOW}示例:${NC}
    # 交互式部署
    sudo ./deploy_cn.sh

    # 仅部署服务端
    sudo ./deploy_cn.sh -m server --server-dir /path/to/HDService

    # 仅部署网页客户端
    sudo ./deploy_cn.sh -m client -s 192.168.1.100

    # 完整部署 (服务端 + 客户端)
    sudo ./deploy_cn.sh -m all -s 192.168.1.100 --server-dir /path/to/HDService

    # 自动部署 (跳过确认)
    sudo ./deploy_cn.sh -s 192.168.1.100 --server-dir /path/to/HDService -y

${YELLOW}注意事项:${NC}
    - 脚本需要 root 权限运行
    - 推荐在 Ubuntu 系统上使用
    - 服务端部署会自动安装依赖
    - 客户端部署会自动安装 Nginx（如未安装）
    - 部署完成后通过 http://IP:端口 访问

EOF
    exit 0
}

# 解析命令行参数
parse_args() {
    SERVER_IP=""
    NGINX_PORT="$DEFAULT_PORT"
    DEPLOY_DIR="$DEFAULT_DEPLOY_DIR"
    WS_PORT="$DEFAULT_WS_PORT"
    SERVER_DIR="$DEFAULT_SERVER_DIR"
    DEPLOY_MODE="all"  # all, server, client
    AUTO_YES=false

    while [ $# -gt 0 ]; do
        case $1 in
            -m|--mode)
                DEPLOY_MODE="$2"
                if [ "$DEPLOY_MODE" != "all" ] && [ "$DEPLOY_MODE" != "server" ] && [ "$DEPLOY_MODE" != "client" ]; then
                    print_error "无效的部署模式: $DEPLOY_MODE (可选: all, server, client)"
                    exit 1
                fi
                shift 2
                ;;
            -s|--server-ip)
                SERVER_IP="$2"
                shift 2
                ;;
            -p|--port)
                NGINX_PORT="$2"
                shift 2
                ;;
            -d|--deploy-dir)
                DEPLOY_DIR="$2"
                shift 2
                ;;
            --server-dir)
                SERVER_DIR="$2"
                shift 2
                ;;
            -y|--yes)
                AUTO_YES=true
                shift
                ;;
            -r|--run)
                RUN_AFTER_DEPLOY=true
                shift
                ;;
            -h|--help)
                show_help
                ;;
            *)
                print_error "未知选项: $1"
                echo "使用 -h 或 --help 查看帮助信息"
                exit 1
                ;;
        esac
    done
}

# 检查 root 权限
check_root() {
    if [ "$EUID" -ne 0 ]; then
        print_error "请使用 root 权限运行此脚本"
        print_info "用法: sudo ./deploy_cn.sh"
        exit 1
    fi
}

# 检查是否为 Ubuntu 系统
check_ubuntu() {
    if [ ! -f /etc/os-release ]; then
        print_error "无法检测操作系统"
        exit 1
    fi

    . /etc/os-release
    if [ "$ID" != "ubuntu" ]; then
        print_warn "检测到非 Ubuntu 系统: $ID"
        if [ "$AUTO_YES" = false ]; then
            printf '是否继续部署？(y/n): ' && read continue_deploy
            if [ "$continue_deploy" != "y" ]; then
                print_info "部署已取消"
                exit 0
            fi
        else
            print_info "自动模式：在非 Ubuntu 系统上继续"
        fi
    else
        print_info "检测到 Ubuntu 系统: $VERSION"
    fi
}

# 自动检测本机 IP 地址
detect_local_ip() {
    local ip=""

    # 尝试从默认路由接口获取 IP
    if command -v ip > /dev/null 2>&1; then
        ip=$(ip route get 1.1.1.1 2>/dev/null | sed -n 's/.*src \([0-9.]*\).*/\1/p' | head -1)
    fi

    # 备选方案：hostname -I
    if [ -z "$ip" ] && command -v hostname > /dev/null 2>&1; then
        ip=$(hostname -I 2>/dev/null | awk '{print $1}')
    fi

    # 备选方案：ifconfig
    if [ -z "$ip" ] && command -v ifconfig > /dev/null 2>&1; then
        ip=$(ifconfig 2>/dev/null | grep -Eo 'inet (addr:)?([0-9]*\.){3}[0-9]*' | grep -Eo '([0-9]*\.){3}[0-9]*' | grep -v '127.0.0.1' | head -1)
    fi

    echo "$ip"
}

# 自动检测 HDService 目录
detect_hdservice_dir() {
    local script_dir="$(cd "$(dirname "$0")" && pwd)"

    for dir in \
        "$script_dir/HDService" \
        "$script_dir/../HDService" \
        "/opt/HDService" \
        /home/*/HDService \
    ; do
        if [ -d "$dir" ] && [ -f "$dir/HDService" ]; then
            echo "$dir"
            return 0
        fi
    done

    echo ""
}

# 显示部署模式菜单
show_deploy_menu() {
    # 如果命令行已提供关键参数则跳过菜单
    if [ -n "$SERVER_IP" ] || [ -n "$SERVER_DIR" ] || [ "$AUTO_YES" = true ]; then
        return 0
    fi

    echo ""
    echo "========================================="
    printf '%b\n' "${BLUE}  HandDriver Web 部署工具${NC}"
    echo "========================================="
    echo ""
    echo "请选择部署模式："
    echo ""
    printf '%b\n' "  ${GREEN}1)${NC} 快速部署（推荐）"
    echo "     - 自动检测 IP 和服务目录"
    echo "     - 使用默认端口和路径"
    echo "     - 最少的用户交互"
    echo ""
    printf '%b\n' "  ${YELLOW}2)${NC} 自定义部署"
    echo "     - 手动配置所有参数"
    echo "     - 完全控制部署过程"
    echo ""
    printf '请输入选项 [1]: ' && read deploy_choice

    case $deploy_choice in
        2)
            print_info "已选择自定义部署模式"
            QUICK_DEPLOY=false
            ;;
        *)
            print_info "已选择快速部署模式"
            QUICK_DEPLOY=true
            setup_quick_deploy
            ;;
    esac
    echo ""
}

# 配置快速部署（使用自动检测的值）
setup_quick_deploy() {
    print_info "正在自动检测配置..."

    # 自动检测服务器 IP
    local detected_ip=$(detect_local_ip)
    if [ -n "$detected_ip" ]; then
        SERVER_IP="$detected_ip"
        print_info "检测到服务器 IP: $SERVER_IP"
    else
        print_warn "无法自动检测 IP 地址"
        printf '请输入服务器 IP 地址: ' && read SERVER_IP
        while [ -z "$SERVER_IP" ]; do
            print_warn "IP 地址不能为空"
            printf '请输入服务器 IP 地址: ' && read SERVER_IP
        done
    fi

    # 自动检测 HDService 目录
    local detected_dir=$(detect_hdservice_dir)
    if [ -n "$detected_dir" ]; then
        SERVER_DIR="$detected_dir"
        print_info "检测到 HDService 目录: $SERVER_DIR"
    else
        print_warn "无法自动检测 HDService 目录"
        printf '请输入 HDService 目录路径: ' && read SERVER_DIR
        while [ -z "$SERVER_DIR" ] || [ ! -d "$SERVER_DIR" ]; do
            if [ -z "$SERVER_DIR" ]; then
                print_warn "目录路径不能为空"
            else
                print_warn "目录不存在: $SERVER_DIR"
            fi
            printf '请输入 HDService 目录路径: ' && read SERVER_DIR
        done
    fi

    # 使用默认值
    NGINX_PORT="$DEFAULT_PORT"
    DEPLOY_DIR="$DEFAULT_DEPLOY_DIR"
    WS_PORT="$DEFAULT_WS_PORT"
    DEPLOY_MODE="all"
    RUN_AFTER_DEPLOY=true

    # 显示检测到的配置
    echo ""
    echo "========================================="
    echo "快速部署配置："
    echo "  服务器 IP: $SERVER_IP"
    echo "  HDService 目录: $SERVER_DIR"
    echo "  Nginx 端口: $NGINX_PORT"
    echo "  部署目录: $DEPLOY_DIR"
    echo "  WebSocket: ws://$SERVER_IP:$WS_PORT"
    echo "  部署后自动启动: 是"
    echo "========================================="
    echo ""

    printf '是否使用此配置？(Y/n): ' && read confirm
    if [ "$confirm" = "n" ] || [ "$confirm" = "N" ]; then
        print_info "切换到自定义部署..."
        QUICK_DEPLOY=false
        # 重置自动检测的值
        SERVER_IP=""
        SERVER_DIR=""
        RUN_AFTER_DEPLOY=false
    else
        AUTO_YES=true
    fi
}

# 检查 HDWebClient 目录
check_webclient() {
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
    WEBCLIENT_DIR="$SCRIPT_DIR/HDWebClient"

    if [ ! -d "$WEBCLIENT_DIR" ]; then
        print_error "未找到 HDWebClient 目录: $WEBCLIENT_DIR"
        print_info "请确保 HDWebClient 目录与脚本在同一目录下"
        exit 1
    fi

    if [ ! -f "$WEBCLIENT_DIR/index.html" ]; then
        print_error "HDWebClient 目录不完整，缺少 index.html"
        exit 1
    fi

    print_info "找到 HDWebClient 目录: $WEBCLIENT_DIR"
}

# 检测 Ubuntu 版本
detect_ubuntu_version() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        UBUNTU_VERSION_ID="$VERSION_ID"
        UBUNTU_VERSION_MAJOR="${VERSION_ID%%.*}"
        print_info "检测到 Ubuntu 版本: $VERSION_ID"
    else
        print_warn "无法检测 Ubuntu 版本，默认按 Ubuntu 22 处理"
        UBUNTU_VERSION_ID="22.04"
        UBUNTU_VERSION_MAJOR="22"
    fi
}

# 检测系统架构
detect_architecture() {
    ARCH=$(uname -m)
    case $ARCH in
        x86_64)
            ARCH_TYPE="amd64"
            print_info "检测到系统架构: x86_64 (amd64)"
            ;;
        aarch64|arm64)
            ARCH_TYPE="arm64"
            print_info "检测到系统架构: ARM64"
            ;;
        *)
            print_warn "未知架构: $ARCH，默认按 x86_64 处理"
            ARCH_TYPE="amd64"
            ;;
    esac
}

# 检查 HDService 目录
check_hdservice() {
    if [ -z "$SERVER_DIR" ]; then
        print_error "未指定服务端目录"
        print_info "请使用 --server-dir 指定 HDService 目录"
        exit 1
    fi

    if [ ! -d "$SERVER_DIR" ]; then
        print_error "服务端目录不存在: $SERVER_DIR"
        exit 1
    fi

    if [ ! -f "$SERVER_DIR/HDService" ]; then
        print_error "HDService 目录不完整，缺少 HDService 可执行文件"
        exit 1
    fi

    print_info "找到 HDService 目录: $SERVER_DIR"
}

# 安装服务端依赖
install_server_dependencies() {
    print_info "正在安装服务端依赖..."

    # 更新软件包列表
    apt-get update

    # 安装依赖
    print_info "正在安装编译工具和库..."
    apt-get install -y build-essential libboost-all-dev libopencv-dev libspdlog-dev \
        libfmt-dev libgoogle-glog-dev libopenblas-dev libdlib-dev libjsoncpp-dev \
        libfltk1.3-dev libyaml-cpp-dev python3-pip python3-dev cmake vim git \
        libssl-dev libcurl4-openssl-dev libwebsocketpp-dev || {
        print_warn "部分依赖安装失败，尝试修复..."
        apt --fix-broken install -y
        apt-get install -y build-essential libboost-all-dev libopencv-dev libspdlog-dev \
            libfmt-dev libgoogle-glog-dev libopenblas-dev libdlib-dev libjsoncpp-dev \
            libfltk1.3-dev libyaml-cpp-dev python3-pip python3-dev cmake vim git \
            libssl-dev libcurl4-openssl-dev libwebsocketpp-dev
    }

    print_info "依赖安装完成"
}

# Ubuntu 版本特定操作
install_ubuntu_specific() {
    detect_ubuntu_version
    detect_architecture

    case $UBUNTU_VERSION_MAJOR in
        20)
            print_info "执行 Ubuntu 20 特定操作：安装 protobuf 3.12.4..."
            cd /tmp
            if [ ! -f "protobuf-all-3.12.4.tar.gz" ]; then
                wget https://github.com/protocolbuffers/protobuf/releases/download/v3.12.4/protobuf-all-3.12.4.tar.gz
            fi
            tar -xzf protobuf-all-3.12.4.tar.gz
            cd protobuf-3.12.4
            ./configure
            make -j$(nproc)
            make install
            ldconfig
            cd "$SERVER_DIR"
            print_info "protobuf 安装完成"
            ;;
        22)
            print_info "Ubuntu 22：无需特定操作"
            ;;
        24)
            if [ "$ARCH_TYPE" = "amd64" ]; then
                print_info "执行 Ubuntu 24 (amd64) 特定操作..."
                if [ -f "$SERVER_DIR/libprotobuf23_3.12.4-1ubuntu7_amd64.deb" ]; then
                    dpkg -i "$SERVER_DIR/libprotobuf23_3.12.4-1ubuntu7_amd64.deb"
                    print_info "libprotobuf 安装完成"
                else
                    print_warn "未找到 libprotobuf23_3.12.4-1ubuntu7_amd64.deb，跳过"
                fi
            else
                print_info "执行 Ubuntu 24 (arm64) 特定操作：编译 protobuf..."
                if [ -f "$SERVER_DIR/protobuf-cpp-3.12.4.tar.gz" ]; then
                    cd "$SERVER_DIR"
                    tar -xzf protobuf-cpp-3.12.4.tar.gz
                    cd protobuf-3.12.4
                    ./configure --prefix=/usr/local
                    make -j$(nproc)
                    make install
                    ldconfig
                    cd "$SERVER_DIR"
                    print_info "protobuf 编译安装完成"
                else
                    print_warn "未找到 protobuf-cpp-3.12.4.tar.gz，跳过"
                fi
            fi
            ;;
        *)
            print_warn "未知 Ubuntu 版本 $UBUNTU_VERSION_MAJOR，跳过特定操作"
            ;;
    esac
}

# 配置 udev 规则
configure_udev_rules() {
    print_info "正在配置 USB 设备规则..."

    if [ -f "$SERVER_DIR/80-usb-serial.rules" ]; then
        cp "$SERVER_DIR/80-usb-serial.rules" /etc/udev/rules.d/
        udevadm control --reload-rules
        udevadm trigger
        print_info "udev 规则配置完成"
    else
        print_warn "未找到 80-usb-serial.rules，跳过 udev 配置"
    fi
}

# 设置 HDService 权限
setup_hdservice_permissions() {
    print_info "正在设置 HDService 目录权限..."

    chmod -R 755 "$SERVER_DIR"
    chmod +x "$SERVER_DIR/HDService"

    print_info "权限设置完成"
}

# 创建 HDService systemd 服务（可选）
create_hdservice_systemd() {
    print_info "正在创建 HDService systemd 服务..."

    SYSTEMD_SERVICE="/etc/systemd/system/hdservice.service"

    cat > "$SYSTEMD_SERVICE" << EOF
[Unit]
Description=HandDriver Service
After=network.target

[Service]
Type=simple
WorkingDirectory=$SERVER_DIR
ExecStart=$SERVER_DIR/HDService
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    print_info "systemd 服务已创建"
    print_info "服务管理命令："
    print_info "  启动服务: sudo systemctl start hdservice"
    print_info "  停止服务: sudo systemctl stop hdservice"
    print_info "  开机自启: sudo systemctl enable hdservice"
}

# 部署服务端
deploy_server() {
    print_info "========================================="
    print_info "开始部署服务端..."
    print_info "========================================="

    check_hdservice
    install_server_dependencies
    install_ubuntu_specific
    configure_udev_rules
    setup_hdservice_permissions
    ldconfig

    # 询问是否创建 systemd 服务
    if [ "$AUTO_YES" = false ]; then
        printf '是否创建 systemd 服务以便管理 HDService？(y/n): ' && read create_service
        if [ "$create_service" = "y" ]; then
            create_hdservice_systemd
        fi
    else
        create_hdservice_systemd
    fi

    print_info "服务端部署完成"
    print_info "启动服务端: cd $SERVER_DIR && ./HDService"
}

# 安装 Nginx
install_nginx() {
    if command -v nginx > /dev/null 2>&1; then
        print_info "Nginx 已安装: $(nginx -v 2>&1)"
        return 0
    fi

    print_info "正在安装 Nginx..."
    apt-get update
    apt-get install -y nginx

    if command -v nginx > /dev/null 2>&1; then
        print_info "Nginx 安装成功"
    else
        print_error "Nginx 安装失败"
        exit 1
    fi
}

# 获取用户配置
get_user_config() {
    echo ""
    echo "========================================="
    echo "  HandDriver Web 部署配置"
    echo "========================================="
    echo ""

    # 交互式选择部署模式（如未指定）
    if [ "$DEPLOY_MODE" = "all" ] && [ "$AUTO_YES" = false ]; then
        echo "请选择部署模式："
        echo "  1) all    - 部署服务端和网页客户端"
        echo "  2) server - 仅部署服务端"
        echo "  3) client - 仅部署网页客户端"
        printf '请输入选项 [默认: 1]: ' && read mode_choice
        case $mode_choice in
            2|server)
                DEPLOY_MODE="server"
                ;;
            3|client)
                DEPLOY_MODE="client"
                ;;
            *)
                DEPLOY_MODE="all"
                ;;
        esac
        echo ""
    fi

    # 服务端配置
    if [ "$DEPLOY_MODE" = "all" ] || [ "$DEPLOY_MODE" = "server" ]; then
        if [ -z "$SERVER_DIR" ] && [ "$AUTO_YES" = false ]; then
            printf '请输入 HDService 目录路径: ' && read SERVER_DIR
            while [ -z "$SERVER_DIR" ] || [ ! -d "$SERVER_DIR" ]; do
                if [ -z "$SERVER_DIR" ]; then
                    print_warn "目录路径不能为空"
                else
                    print_warn "目录不存在: $SERVER_DIR"
                fi
                printf '请输入 HDService 目录路径: ' && read SERVER_DIR
            done
        fi
    fi

    # 客户端配置
    if [ "$DEPLOY_MODE" = "all" ] || [ "$DEPLOY_MODE" = "client" ]; then
        if [ -z "$SERVER_IP" ] && [ "$AUTO_YES" = false ]; then
            # WebSocket 服务器地址
            printf '请输入服务器 IP 地址: ' && read SERVER_IP
            while [ -z "$SERVER_IP" ]; do
                print_warn "IP 地址不能为空"
                printf '请输入服务器 IP 地址: ' && read SERVER_IP
            done

            # Nginx 监听端口
            printf "请输入 Nginx 监听端口 [默认: $DEFAULT_PORT]: " && read input_port
            if [ -n "$input_port" ]; then
                NGINX_PORT="$input_port"
            fi

            # 部署目录
            printf "请输入网页客户端部署目录 [默认: $DEFAULT_DEPLOY_DIR]: " && read input_dir
            if [ -n "$input_dir" ]; then
                DEPLOY_DIR="$input_dir"
            fi
        fi

        # 校验服务器 IP
        if [ -z "$SERVER_IP" ]; then
            print_error "服务器 IP 地址不能为空"
            exit 1
        fi
    fi

    # 显示配置汇总
    echo ""
    echo "========================================="
    echo "配置汇总："
    echo "  部署模式: $DEPLOY_MODE"
    if [ "$DEPLOY_MODE" = "all" ] || [ "$DEPLOY_MODE" = "server" ]; then
        echo "  服务端目录: $SERVER_DIR"
    fi
    if [ "$DEPLOY_MODE" = "all" ] || [ "$DEPLOY_MODE" = "client" ]; then
        echo "  服务器 IP: $SERVER_IP"
        echo "  Nginx 端口: $NGINX_PORT"
        echo "  部署目录: $DEPLOY_DIR"
        echo "  WebSocket: ws://$SERVER_IP:$WS_PORT"
    fi
    echo "========================================="
    echo ""

    # 确认配置
    if [ "$AUTO_YES" = false ]; then
        printf '确认以上配置？(y/n): ' && read confirm
        if [ "$confirm" != "y" ]; then
            print_info "部署已取消"
            exit 0
        fi
    else
        print_info "自动模式：使用以上配置继续"
    fi
}

# 创建部署目录并复制文件
deploy_files() {
    print_info "正在创建部署目录: $DEPLOY_DIR"
    mkdir -p "$DEPLOY_DIR"

    print_info "正在复制 HDWebClient 文件到部署目录..."
    cp -r "$WEBCLIENT_DIR"/* "$DEPLOY_DIR/"

    print_info "文件复制完成"
}

# 配置 server-config.json
configure_server_config() {
    print_info "正在配置 server-config.json..."

    SERVER_CONFIG="$DEPLOY_DIR/server-config.json"

    cat > "$SERVER_CONFIG" << EOF
{
  "serverUrl": "ws://$SERVER_IP:$WS_PORT"
}
EOF

    print_info "server-config.json 配置完成"
    print_info "WebSocket 地址: ws://$SERVER_IP:$WS_PORT"
}

# 创建 Nginx 配置
configure_nginx() {
    print_info "正在创建 Nginx 站点配置..."

    NGINX_CONF="/etc/nginx/conf.d/handdriver.conf"

    cat > "$NGINX_CONF" << EOF
server {
    listen $NGINX_PORT;
    server_name _;

    root $DEPLOY_DIR;
    index index.html;

    location / {
        try_files \$uri \$uri/ /index.html;
    }

    # 静态资源缓存
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
EOF

    print_info "Nginx 配置文件已创建: $NGINX_CONF"
}

# 修改 Nginx 主配置
modify_nginx_main_config() {
    print_info "正在修改 Nginx 主配置..."

    NGINX_MAIN_CONF="/etc/nginx/nginx.conf"

    if grep -q "^user www-data;" "$NGINX_MAIN_CONF"; then
        sed -i 's/^user www-data;/user root;/' "$NGINX_MAIN_CONF"
        print_info "Nginx 用户已改为 root"
    elif grep -q "^user root;" "$NGINX_MAIN_CONF"; then
        print_info "Nginx 用户已经是 root"
    else
        print_warn "未找到用户配置，请手动检查 $NGINX_MAIN_CONF"
    fi
}

# 测试并重载 Nginx
reload_nginx() {
    print_info "正在测试 Nginx 配置..."

    if nginx -t; then
        print_info "Nginx 配置测试通过"
    else
        print_error "Nginx 配置测试失败"
        print_info "请检查配置文件: /etc/nginx/conf.d/handdriver.conf"
        exit 1
    fi

    print_info "正在重载 Nginx 服务..."
    systemctl reload nginx

    if systemctl is-active --quiet nginx; then
        print_info "Nginx 服务运行正常"
    else
        print_warn "Nginx 服务未运行，尝试启动..."
        systemctl start nginx

        if systemctl is-active --quiet nginx; then
            print_info "Nginx 服务启动成功"
        else
            print_error "Nginx 服务启动失败"
            print_info "请查看日志: journalctl -u nginx -n 50"
            exit 1
        fi
    fi
}

# 显示部署结果
show_result() {
    echo ""
    echo "========================================="
    printf '%b\n' "${GREEN}部署完成！${NC}"
    echo "========================================="
    echo ""

    if [ "$DEPLOY_MODE" = "all" ] || [ "$DEPLOY_MODE" = "server" ]; then
        echo "服务端信息："
        echo "  HDService 目录: $SERVER_DIR"
        echo "  启动命令: cd $SERVER_DIR && ./HDService"
        if [ -f "/etc/systemd/system/hdservice.service" ]; then
            echo "  systemd 服务: sudo systemctl start hdservice"
        fi
        echo ""
    fi

    if [ "$DEPLOY_MODE" = "all" ] || [ "$DEPLOY_MODE" = "client" ]; then
        echo "网页客户端信息："
        echo "  访问地址: http://$SERVER_IP:$NGINX_PORT/"
        echo ""
        echo "配置文件："
        echo "  部署目录: $DEPLOY_DIR"
        echo "  Nginx 配置: /etc/nginx/conf.d/handdriver.conf"
        echo "  服务配置: $DEPLOY_DIR/server-config.json"
        echo ""
        echo "验证方法："
        echo "  1. 检查 Nginx 配置: sudo nginx -t"
        echo "  2. 访问页面: http://$SERVER_IP:$NGINX_PORT/"
        echo "  3. 检查配置: http://$SERVER_IP:$NGINX_PORT/server-config.json"
        echo ""
    fi

    echo "常用命令："
    if [ "$DEPLOY_MODE" = "all" ] || [ "$DEPLOY_MODE" = "server" ]; then
        echo "  启动服务端: cd $SERVER_DIR && ./HDService"
        if [ -f "/etc/systemd/system/hdservice.service" ]; then
            echo "  管理服务: sudo systemctl {start|stop|restart|status} hdservice"
        fi
    fi
    if [ "$DEPLOY_MODE" = "all" ] || [ "$DEPLOY_MODE" = "client" ]; then
        echo "  重启 Nginx: sudo systemctl restart nginx"
        echo "  查看 Nginx 日志: sudo journalctl -u nginx -f"
        echo "  检查 Nginx 状态: sudo systemctl status nginx"
    fi
    echo ""
    echo "========================================="
}

# 部署后启动服务器
start_server() {
    print_info "正在启动 HDService 服务..."

    # 检查 systemd 服务是否存在
    if [ -f "/etc/systemd/system/hdservice.service" ]; then
        systemctl start hdservice
        sleep 2
        if systemctl is-active --quiet hdservice; then
            print_info "HDService 已通过 systemd 成功启动"
        else
            print_warn "通过 systemd 启动失败，尝试直接运行..."
            cd "$SERVER_DIR" && nohup ./HDService > /var/log/hdservice.log 2>&1 &
            sleep 2
            if pgrep -f "HDService" > /dev/null; then
                print_info "HDService 已在后台成功启动"
            else
                print_error "HDService 启动失败"
                return 1
            fi
        fi
    else
        # 直接后台运行
        cd "$SERVER_DIR" && nohup ./HDService > /var/log/hdservice.log 2>&1 &
        sleep 2
        if pgrep -f "HDService" > /dev/null; then
            print_info "HDService 已在后台成功启动"
            print_info "日志文件: /var/log/hdservice.log"
        else
            print_error "HDService 启动失败"
            return 1
        fi
    fi
}

# 打开浏览器（以实际用户身份运行，而非 root）
open_browser() {
    local url="http://$SERVER_IP:$NGINX_PORT/"
    print_info "正在打开浏览器: $url"

    # 获取实际调用 sudo 的用户
    local real_user="${SUDO_USER:-$USER}"

    # 检测可用的浏览器命令
    local browser_cmd=""
    if command -v xdg-open > /dev/null 2>&1; then
        browser_cmd="xdg-open"
    elif command -v sensible-browser > /dev/null 2>&1; then
        browser_cmd="sensible-browser"
    elif command -v gnome-open > /dev/null 2>&1; then
        browser_cmd="gnome-open"
    elif command -v firefox > /dev/null 2>&1; then
        browser_cmd="firefox"
    elif command -v chromium-browser > /dev/null 2>&1; then
        browser_cmd="chromium-browser"
    elif command -v google-chrome > /dev/null 2>&1; then
        browser_cmd="google-chrome"
    else
        print_warn "未找到浏览器，请手动打开: $url"
        return 1
    fi

    # 以实际用户身份运行浏览器，确保能访问桌面会话
    if [ "$real_user" != "root" ] && [ -n "$real_user" ]; then
        su "$real_user" -c "DISPLAY=${DISPLAY:-:0} $browser_cmd '$url'" > /dev/null 2>&1 &
    else
        $browser_cmd "$url" > /dev/null 2>&1 &
    fi

    print_info "浏览器已打开"
}

# 部署完成后运行服务器并打开浏览器
run_after_deploy() {
    echo ""
    print_info "========================================="
    print_info "正在启动部署后服务..."
    print_info "========================================="

    # 如果部署了服务端则启动服务器
    if [ "$DEPLOY_MODE" = "all" ] || [ "$DEPLOY_MODE" = "server" ]; then
        start_server
    fi

    # 如果部署了客户端则打开浏览器
    if [ "$DEPLOY_MODE" = "all" ] || [ "$DEPLOY_MODE" = "client" ]; then
        # 等待服务器就绪
        sleep 2
        open_browser
    fi

    echo ""
    print_info "部署后服务已启动"
}

# 部署网页客户端
deploy_client() {
    print_info "========================================="
    print_info "开始部署网页客户端..."
    print_info "========================================="

    # 1. 前置检查
    check_webclient

    # 2. 安装 Nginx 并修改主配置
    install_nginx
    modify_nginx_main_config

    # 3. 部署文件并配置
    deploy_files
    configure_server_config
    configure_nginx

    # 4. 重载 Nginx 使配置生效
    reload_nginx

    print_info "网页客户端部署完成"
}

# 主函数
main() {
    # 解析命令行参数
    parse_args "$@"

    print_info "开始 HandDriver Web 部署..."
    echo ""

    check_root
    check_ubuntu

    # 显示部署模式菜单（快速或自定义）
    show_deploy_menu

    # 获取配置（快速部署模式下跳过）
    if [ "$QUICK_DEPLOY" != true ]; then
        get_user_config
    fi

    # 根据模式执行部署
    case $DEPLOY_MODE in
        all)
            deploy_server
            echo ""
            deploy_client
            ;;
        server)
            deploy_server
            ;;
        client)
            deploy_client
            ;;
    esac

    show_result

    # 部署完成后运行服务器并打开浏览器
    if [ "$RUN_AFTER_DEPLOY" = true ]; then
        run_after_deploy
    elif [ "$AUTO_YES" = false ]; then
        printf '是否立即启动服务器并打开浏览器？(Y/n): ' && read run_now
        if [ "$run_now" != "n" ] && [ "$run_now" != "N" ]; then
            run_after_deploy
        fi
    fi
}

# 执行主函数
main "$@"
