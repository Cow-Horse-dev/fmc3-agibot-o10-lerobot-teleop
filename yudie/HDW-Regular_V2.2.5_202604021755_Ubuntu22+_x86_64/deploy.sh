#!/bin/sh

#############################################
# HandDriver Web Deployment Script
# Purpose: Deploy server and web client on Ubuntu
#############################################

set -e

# Color definitions
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default configuration
DEFAULT_PORT=8088
DEFAULT_DEPLOY_DIR="/var/www/handdriver"
DEFAULT_WS_PORT=7789
DEFAULT_SERVER_DIR=""
RUN_AFTER_DEPLOY=false
QUICK_DEPLOY=false

# Print functions
print_info() {
    printf '%b\n' "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    printf '%b\n' "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    printf '%b\n' "${RED}[ERROR]${NC} $1"
}

# Show help information
show_help() {
    cat << EOF
${BLUE}HandDriver Web Deployment Script${NC}

${YELLOW}Usage:${NC}
    sudo ./deploy.sh [options]

${YELLOW}Options:${NC}
    -m, --mode MODE           Deploy mode: all, server, client (default: all)
    -s, --server-ip IP        Server IP address (required for client)
    -p, --port PORT           Nginx listen port (default: $DEFAULT_PORT)
    -d, --deploy-dir DIR      Web client deploy directory (default: $DEFAULT_DEPLOY_DIR)
    --server-dir DIR          HDService directory path
    -r, --run                 Run server and open browser after deployment
    -y, --yes                 Skip all confirmation prompts
    -h, --help                Show this help message

${YELLOW}Examples:${NC}
    # Interactive deployment
    sudo ./deploy.sh

    # Deploy server only
    sudo ./deploy.sh -m server --server-dir /path/to/HDService

    # Deploy web client only
    sudo ./deploy.sh -m client -s 192.168.1.100

    # Full deployment (server + client)
    sudo ./deploy.sh -m all -s 192.168.1.100 --server-dir /path/to/HDService

    # Auto deployment (skip confirmations)
    sudo ./deploy.sh -s 192.168.1.100 --server-dir /path/to/HDService -y

${YELLOW}Notes:${NC}
    - Script requires root privileges
    - Recommended for Ubuntu systems
    - Server deployment will auto-install dependencies
    - Client deployment will auto-install Nginx if not installed
    - Access via http://IP:PORT after deployment

EOF
    exit 0
}

# Parse command line arguments
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
                    print_error "Invalid deploy mode: $DEPLOY_MODE (valid: all, server, client)"
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
                print_error "Unknown option: $1"
                echo "Use -h or --help to see help message"
                exit 1
                ;;
        esac
    done
}

# Check root privileges
check_root() {
    if [ "$EUID" -ne 0 ]; then
        print_error "Please run this script with root privileges"
        print_info "Usage: sudo ./deploy.sh"
        exit 1
    fi
}

# Check if Ubuntu system
check_ubuntu() {
    if [ ! -f /etc/os-release ]; then
        print_error "Cannot detect operating system"
        exit 1
    fi

    . /etc/os-release
    if [ "$ID" != "ubuntu" ]; then
        print_warn "Non-Ubuntu system detected: $ID"
        if [ "$AUTO_YES" = false ]; then
            printf 'Continue deployment? (y/n): ' && read continue_deploy
            if [ "$continue_deploy" != "y" ]; then
                print_info "Deployment cancelled"
                exit 0
            fi
        else
            print_info "Auto mode: Continuing on non-Ubuntu system"
        fi
    else
        print_info "Ubuntu system detected: $VERSION"
    fi
}

# Auto detect local IP address
detect_local_ip() {
    local ip=""

    # Try to get IP from default route interface
    if command -v ip > /dev/null 2>&1; then
        ip=$(ip route get 1.1.1.1 2>/dev/null | sed -n 's/.*src \([0-9.]*\).*/\1/p' | head -1)
    fi

    # Fallback to hostname -I
    if [ -z "$ip" ] && command -v hostname > /dev/null 2>&1; then
        ip=$(hostname -I 2>/dev/null | awk '{print $1}')
    fi

    # Fallback to ifconfig
    if [ -z "$ip" ] && command -v ifconfig > /dev/null 2>&1; then
        ip=$(ifconfig 2>/dev/null | grep -Eo 'inet (addr:)?([0-9]*\.){3}[0-9]*' | grep -Eo '([0-9]*\.){3}[0-9]*' | grep -v '127.0.0.1' | head -1)
    fi

    echo "$ip"
}

# Auto detect HDService directory
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

# Show deployment mode menu
show_deploy_menu() {
    # Skip menu if command line args provided key parameters
    if [ -n "$SERVER_IP" ] || [ -n "$SERVER_DIR" ] || [ "$AUTO_YES" = true ]; then
        return 0
    fi

    echo ""
    echo "========================================="
    printf '%b\n' "${BLUE}  HandDriver Web Deployment${NC}"
    echo "========================================="
    echo ""
    echo "Please select deployment mode:"
    echo ""
    printf '%b\n' "  ${GREEN}1)${NC} Quick Deploy (Recommended)"
    echo "     - Auto-detect IP and server directory"
    echo "     - Use default ports and paths"
    echo "     - Minimal user interaction"
    echo ""
    printf '%b\n' "  ${YELLOW}2)${NC} Custom Deploy"
    echo "     - Manually configure all parameters"
    echo "     - Full control over deployment"
    echo ""
    printf 'Enter your choice [1]: ' && read deploy_choice

    case $deploy_choice in
        2)
            print_info "Custom deployment mode selected"
            QUICK_DEPLOY=false
            ;;
        *)
            print_info "Quick deployment mode selected"
            QUICK_DEPLOY=true
            setup_quick_deploy
            ;;
    esac
    echo ""
}

# Setup quick deploy with auto-detected values
setup_quick_deploy() {
    print_info "Auto-detecting configuration..."

    # Auto-detect server IP
    local detected_ip=$(detect_local_ip)
    if [ -n "$detected_ip" ]; then
        SERVER_IP="$detected_ip"
        print_info "Detected server IP: $SERVER_IP"
    else
        print_warn "Could not auto-detect IP address"
        printf 'Enter server IP address: ' && read SERVER_IP
        while [ -z "$SERVER_IP" ]; do
            print_warn "IP address cannot be empty"
            printf 'Enter server IP address: ' && read SERVER_IP
        done
    fi

    # Auto-detect HDService directory
    local detected_dir=$(detect_hdservice_dir)
    if [ -n "$detected_dir" ]; then
        SERVER_DIR="$detected_dir"
        print_info "Detected HDService directory: $SERVER_DIR"
    else
        print_warn "Could not auto-detect HDService directory"
        printf 'Enter HDService directory path: ' && read SERVER_DIR
        while [ -z "$SERVER_DIR" ] || [ ! -d "$SERVER_DIR" ]; do
            if [ -z "$SERVER_DIR" ]; then
                print_warn "Directory path cannot be empty"
            else
                print_warn "Directory not found: $SERVER_DIR"
            fi
            printf 'Enter HDService directory path: ' && read SERVER_DIR
        done
    fi

    # Use default values for other parameters
    NGINX_PORT="$DEFAULT_PORT"
    DEPLOY_DIR="$DEFAULT_DEPLOY_DIR"
    WS_PORT="$DEFAULT_WS_PORT"
    DEPLOY_MODE="all"
    RUN_AFTER_DEPLOY=true

    # Show detected configuration
    echo ""
    echo "========================================="
    echo "Quick Deploy Configuration:"
    echo "  Server IP: $SERVER_IP"
    echo "  HDService directory: $SERVER_DIR"
    echo "  Nginx port: $NGINX_PORT"
    echo "  Deploy directory: $DEPLOY_DIR"
    echo "  WebSocket: ws://$SERVER_IP:$WS_PORT"
    echo "  Auto-start after deploy: Yes"
    echo "========================================="
    echo ""

    printf 'Proceed with this configuration? (Y/n): ' && read confirm
    if [ "$confirm" = "n" ] || [ "$confirm" = "N" ]; then
        print_info "Switching to custom deployment..."
        QUICK_DEPLOY=false
        # Reset auto-detected values
        SERVER_IP=""
        SERVER_DIR=""
        RUN_AFTER_DEPLOY=false
    else
        AUTO_YES=true
    fi
}

# Check HDWebClient directory
check_webclient() {
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
    WEBCLIENT_DIR="$SCRIPT_DIR/HDWebClient"

    if [ ! -d "$WEBCLIENT_DIR" ]; then
        print_error "HDWebClient directory not found: $WEBCLIENT_DIR"
        print_info "Please ensure HDWebClient directory is in the same directory as the script"
        exit 1
    fi

    if [ ! -f "$WEBCLIENT_DIR/index.html" ]; then
        print_error "HDWebClient directory incomplete, missing index.html"
        exit 1
    fi

    print_info "Found HDWebClient directory: $WEBCLIENT_DIR"
}

# Detect Ubuntu version
detect_ubuntu_version() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        UBUNTU_VERSION_ID="$VERSION_ID"
        UBUNTU_VERSION_MAJOR="${VERSION_ID%%.*}"
        print_info "Detected Ubuntu version: $VERSION_ID"
    else
        print_warn "Cannot detect Ubuntu version, assuming Ubuntu 22"
        UBUNTU_VERSION_ID="22.04"
        UBUNTU_VERSION_MAJOR="22"
    fi
}

# Detect system architecture
detect_architecture() {
    ARCH=$(uname -m)
    case $ARCH in
        x86_64)
            ARCH_TYPE="amd64"
            print_info "Detected architecture: x86_64 (amd64)"
            ;;
        aarch64|arm64)
            ARCH_TYPE="arm64"
            print_info "Detected architecture: ARM64"
            ;;
        *)
            print_warn "Unknown architecture: $ARCH, assuming x86_64"
            ARCH_TYPE="amd64"
            ;;
    esac
}

# Check HDService directory
check_hdservice() {
    if [ -z "$SERVER_DIR" ]; then
        print_error "Server directory not specified"
        print_info "Please use --server-dir to specify HDService directory"
        exit 1
    fi

    if [ ! -d "$SERVER_DIR" ]; then
        print_error "Server directory not found: $SERVER_DIR"
        exit 1
    fi

    if [ ! -f "$SERVER_DIR/HDService" ]; then
        print_error "HDService directory incomplete, missing HDService executable"
        exit 1
    fi

    print_info "Found HDService directory: $SERVER_DIR"
}

# Install server dependencies
install_server_dependencies() {
    print_info "Installing server dependencies..."

    # Update package list
    apt-get update

    # Install dependencies
    print_info "Installing build tools and libraries..."
    apt-get install -y build-essential libboost-all-dev libopencv-dev libspdlog-dev \
        libfmt-dev libgoogle-glog-dev libopenblas-dev libdlib-dev libjsoncpp-dev \
        libfltk1.3-dev libyaml-cpp-dev python3-pip python3-dev cmake vim git \
        libssl-dev libcurl4-openssl-dev libwebsocketpp-dev || {
        print_warn "Some dependencies failed to install, attempting to fix..."
        apt --fix-broken install -y
        apt-get install -y build-essential libboost-all-dev libopencv-dev libspdlog-dev \
            libfmt-dev libgoogle-glog-dev libopenblas-dev libdlib-dev libjsoncpp-dev \
            libfltk1.3-dev libyaml-cpp-dev python3-pip python3-dev cmake vim git \
            libssl-dev libcurl4-openssl-dev libwebsocketpp-dev
    }

    print_info "Dependencies installation completed"
}

# Ubuntu version specific operations
install_ubuntu_specific() {
    detect_ubuntu_version
    detect_architecture

    case $UBUNTU_VERSION_MAJOR in
        20)
            print_info "Running Ubuntu 20 specific operations: Installing protobuf 3.12.4..."
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
            print_info "protobuf installation completed"
            ;;
        22)
            print_info "Ubuntu 22: No specific operations required"
            ;;
        24)
            if [ "$ARCH_TYPE" = "amd64" ]; then
                print_info "Running Ubuntu 24 (amd64) specific operations..."
                if [ -f "$SERVER_DIR/libprotobuf23_3.12.4-1ubuntu7_amd64.deb" ]; then
                    dpkg -i "$SERVER_DIR/libprotobuf23_3.12.4-1ubuntu7_amd64.deb"
                    print_info "libprotobuf installation completed"
                else
                    print_warn "libprotobuf23_3.12.4-1ubuntu7_amd64.deb not found, skipping"
                fi
            else
                print_info "Running Ubuntu 24 (arm64) specific operations: Building protobuf..."
                if [ -f "$SERVER_DIR/protobuf-cpp-3.12.4.tar.gz" ]; then
                    cd "$SERVER_DIR"
                    tar -xzf protobuf-cpp-3.12.4.tar.gz
                    cd protobuf-3.12.4
                    ./configure --prefix=/usr/local
                    make -j$(nproc)
                    make install
                    ldconfig
                    cd "$SERVER_DIR"
                    print_info "protobuf build and installation completed"
                else
                    print_warn "protobuf-cpp-3.12.4.tar.gz not found, skipping"
                fi
            fi
            ;;
        *)
            print_warn "Unknown Ubuntu version $UBUNTU_VERSION_MAJOR, skipping specific operations"
            ;;
    esac
}

# Configure udev rules
configure_udev_rules() {
    print_info "Configuring USB device rules..."

    if [ -f "$SERVER_DIR/80-usb-serial.rules" ]; then
        cp "$SERVER_DIR/80-usb-serial.rules" /etc/udev/rules.d/
        udevadm control --reload-rules
        udevadm trigger
        print_info "udev rules configuration completed"
    else
        print_warn "80-usb-serial.rules not found, skipping udev configuration"
    fi
}

# Setup HDService permissions
setup_hdservice_permissions() {
    print_info "Setting HDService directory permissions..."

    chmod -R 755 "$SERVER_DIR"
    chmod +x "$SERVER_DIR/HDService"

    print_info "Permissions setup completed"
}

# Create HDService systemd service (optional)
create_hdservice_systemd() {
    print_info "Creating HDService systemd service..."

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
    print_info "systemd service created"
    print_info "Service management commands:"
    print_info "  Start service: sudo systemctl start hdservice"
    print_info "  Stop service: sudo systemctl stop hdservice"
    print_info "  Enable on boot: sudo systemctl enable hdservice"
}

# Deploy server
deploy_server() {
    print_info "========================================="
    print_info "Starting server deployment..."
    print_info "========================================="

    check_hdservice
    install_server_dependencies
    install_ubuntu_specific
    configure_udev_rules
    setup_hdservice_permissions
    ldconfig

    # Ask whether to create systemd service
    if [ "$AUTO_YES" = false ]; then
        printf 'Create systemd service for HDService management? (y/n): ' && read create_service
        if [ "$create_service" = "y" ]; then
            create_hdservice_systemd
        fi
    else
        create_hdservice_systemd
    fi

    print_info "Server deployment completed"
    print_info "Start server: cd $SERVER_DIR && ./HDService"
}

# Install Nginx
install_nginx() {
    if command -v nginx > /dev/null 2>&1; then
        print_info "Nginx already installed: $(nginx -v 2>&1)"
        return 0
    fi

    print_info "Installing Nginx..."
    apt-get update
    apt-get install -y nginx

    if command -v nginx > /dev/null 2>&1; then
        print_info "Nginx installation successful"
    else
        print_error "Nginx installation failed"
        exit 1
    fi
}

# Get user configuration
get_user_config() {
    echo ""
    echo "========================================="
    echo "  HandDriver Web Deployment Configuration"
    echo "========================================="
    echo ""

    # Interactive mode selection if not specified
    if [ "$DEPLOY_MODE" = "all" ] && [ "$AUTO_YES" = false ]; then
        echo "Select deployment mode:"
        echo "  1) all    - Deploy server and web client"
        echo "  2) server - Deploy server only"
        echo "  3) client - Deploy web client only"
        printf 'Enter your choice [default: 1]: ' && read mode_choice
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

    # Server configuration
    if [ "$DEPLOY_MODE" = "all" ] || [ "$DEPLOY_MODE" = "server" ]; then
        if [ -z "$SERVER_DIR" ] && [ "$AUTO_YES" = false ]; then
            printf 'Enter HDService directory path: ' && read SERVER_DIR
            while [ -z "$SERVER_DIR" ] || [ ! -d "$SERVER_DIR" ]; do
                if [ -z "$SERVER_DIR" ]; then
                    print_warn "Directory path cannot be empty"
                else
                    print_warn "Directory not found: $SERVER_DIR"
                fi
                printf 'Enter HDService directory path: ' && read SERVER_DIR
            done
        fi
    fi

    # Client configuration
    if [ "$DEPLOY_MODE" = "all" ] || [ "$DEPLOY_MODE" = "client" ]; then
        if [ -z "$SERVER_IP" ] && [ "$AUTO_YES" = false ]; then
            # WebSocket server address
            printf 'Enter server IP address: ' && read SERVER_IP
            while [ -z "$SERVER_IP" ]; do
                print_warn "IP address cannot be empty"
                printf 'Enter server IP address: ' && read SERVER_IP
            done

            # Nginx listen port
            printf "Enter Nginx listen port [default: $DEFAULT_PORT]: " && read input_port
            if [ -n "$input_port" ]; then
                NGINX_PORT="$input_port"
            fi

            # Deploy directory
            printf "Enter web client deploy directory [default: $DEFAULT_DEPLOY_DIR]: " && read input_dir
            if [ -n "$input_dir" ]; then
                DEPLOY_DIR="$input_dir"
            fi
        fi

        # Validate server IP
        if [ -z "$SERVER_IP" ]; then
            print_error "Server IP address cannot be empty"
            exit 1
        fi
    fi

    # Show configuration
    echo ""
    echo "========================================="
    echo "Configuration Summary:"
    echo "  Deploy mode: $DEPLOY_MODE"
    if [ "$DEPLOY_MODE" = "all" ] || [ "$DEPLOY_MODE" = "server" ]; then
        echo "  Server directory: $SERVER_DIR"
    fi
    if [ "$DEPLOY_MODE" = "all" ] || [ "$DEPLOY_MODE" = "client" ]; then
        echo "  Server IP: $SERVER_IP"
        echo "  Nginx port: $NGINX_PORT"
        echo "  Deploy directory: $DEPLOY_DIR"
        echo "  WebSocket: ws://$SERVER_IP:$WS_PORT"
    fi
    echo "========================================="
    echo ""

    # Confirm configuration
    if [ "$AUTO_YES" = false ]; then
        printf 'Confirm configuration? (y/n): ' && read confirm
        if [ "$confirm" != "y" ]; then
            print_info "Deployment cancelled"
            exit 0
        fi
    else
        print_info "Auto mode: Proceeding with above configuration"
    fi
}

# Create deploy directory and copy files
deploy_files() {
    print_info "Creating deploy directory: $DEPLOY_DIR"
    mkdir -p "$DEPLOY_DIR"

    print_info "Copying HDWebClient files to deploy directory..."
    cp -r "$WEBCLIENT_DIR"/* "$DEPLOY_DIR/"

    print_info "File copy completed"
}

# Configure server-config.json
configure_server_config() {
    print_info "Configuring server-config.json..."

    SERVER_CONFIG="$DEPLOY_DIR/server-config.json"

    cat > "$SERVER_CONFIG" << EOF
{
  "serverUrl": "ws://$SERVER_IP:$WS_PORT"
}
EOF

    print_info "server-config.json configuration completed"
    print_info "WebSocket URL: ws://$SERVER_IP:$WS_PORT"
}

# Create Nginx configuration
configure_nginx() {
    print_info "Creating Nginx site configuration..."

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

    # Static resource caching
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
EOF

    print_info "Nginx configuration file created: $NGINX_CONF"
}

# Modify Nginx main configuration
modify_nginx_main_config() {
    print_info "Modifying Nginx main configuration..."

    NGINX_MAIN_CONF="/etc/nginx/nginx.conf"

    if grep -q "^user www-data;" "$NGINX_MAIN_CONF"; then
        sed -i 's/^user www-data;/user root;/' "$NGINX_MAIN_CONF"
        print_info "Nginx user changed to root"
    elif grep -q "^user root;" "$NGINX_MAIN_CONF"; then
        print_info "Nginx user is already root"
    else
        print_warn "User config not found, please check $NGINX_MAIN_CONF manually"
    fi
}

# Test and reload Nginx
reload_nginx() {
    print_info "Testing Nginx configuration..."

    if nginx -t; then
        print_info "Nginx configuration test passed"
    else
        print_error "Nginx configuration test failed"
        print_info "Please check config file: /etc/nginx/conf.d/handdriver.conf"
        exit 1
    fi

    print_info "Reloading Nginx service..."
    systemctl reload nginx

    if systemctl is-active --quiet nginx; then
        print_info "Nginx service running normally"
    else
        print_warn "Nginx service not running, attempting to start..."
        systemctl start nginx

        if systemctl is-active --quiet nginx; then
            print_info "Nginx service started successfully"
        else
            print_error "Nginx service failed to start"
            print_info "Please check logs: journalctl -u nginx -n 50"
            exit 1
        fi
    fi
}

# Show deployment result
show_result() {
    echo ""
    echo "========================================="
    printf '%b\n' "${GREEN}Deployment Completed!${NC}"
    echo "========================================="
    echo ""

    if [ "$DEPLOY_MODE" = "all" ] || [ "$DEPLOY_MODE" = "server" ]; then
        echo "Server Information:"
        echo "  HDService directory: $SERVER_DIR"
        echo "  Start command: cd $SERVER_DIR && ./HDService"
        if [ -f "/etc/systemd/system/hdservice.service" ]; then
            echo "  systemd service: sudo systemctl start hdservice"
        fi
        echo ""
    fi

    if [ "$DEPLOY_MODE" = "all" ] || [ "$DEPLOY_MODE" = "client" ]; then
        echo "Web Client Information:"
        echo "  Access URL: http://$SERVER_IP:$NGINX_PORT/"
        echo ""
        echo "Configuration Files:"
        echo "  Deploy directory: $DEPLOY_DIR"
        echo "  Nginx config: /etc/nginx/conf.d/handdriver.conf"
        echo "  Server config: $DEPLOY_DIR/server-config.json"
        echo ""
        echo "Verification:"
        echo "  1. Check Nginx config: sudo nginx -t"
        echo "  2. Access page: http://$SERVER_IP:$NGINX_PORT/"
        echo "  3. Check config: http://$SERVER_IP:$NGINX_PORT/server-config.json"
        echo ""
    fi

    echo "Common Commands:"
    if [ "$DEPLOY_MODE" = "all" ] || [ "$DEPLOY_MODE" = "server" ]; then
        echo "  Start server: cd $SERVER_DIR && ./HDService"
        if [ -f "/etc/systemd/system/hdservice.service" ]; then
            echo "  Manage server: sudo systemctl {start|stop|restart|status} hdservice"
        fi
    fi
    if [ "$DEPLOY_MODE" = "all" ] || [ "$DEPLOY_MODE" = "client" ]; then
        echo "  Restart Nginx: sudo systemctl restart nginx"
        echo "  View Nginx logs: sudo journalctl -u nginx -f"
        echo "  Check Nginx status: sudo systemctl status nginx"
    fi
    echo ""
    echo "========================================="
}

# Start server after deployment
start_server() {
    print_info "Starting HDService server..."

    # Check if systemd service exists
    if [ -f "/etc/systemd/system/hdservice.service" ]; then
        systemctl start hdservice
        sleep 2
        if systemctl is-active --quiet hdservice; then
            print_info "HDService started successfully via systemd"
        else
            print_warn "Failed to start HDService via systemd, trying direct execution..."
            cd "$SERVER_DIR" && nohup ./HDService > /var/log/hdservice.log 2>&1 &
            sleep 2
            if pgrep -f "HDService" > /dev/null; then
                print_info "HDService started successfully in background"
            else
                print_error "Failed to start HDService"
                return 1
            fi
        fi
    else
        # Direct execution in background
        cd "$SERVER_DIR" && nohup ./HDService > /var/log/hdservice.log 2>&1 &
        sleep 2
        if pgrep -f "HDService" > /dev/null; then
            print_info "HDService started successfully in background"
            print_info "Log file: /var/log/hdservice.log"
        else
            print_error "Failed to start HDService"
            return 1
        fi
    fi
}

# Open browser (run as the real user, not root)
open_browser() {
    local url="http://$SERVER_IP:$NGINX_PORT/"
    print_info "Opening browser: $url"

    # Get the real user who invoked sudo
    local real_user="${SUDO_USER:-$USER}"

    # Detect available browser command
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
        print_warn "No browser found, please manually open: $url"
        return 1
    fi

    # Run browser as the real user so it can access the desktop session
    if [ "$real_user" != "root" ] && [ -n "$real_user" ]; then
        su "$real_user" -c "DISPLAY=${DISPLAY:-:0} $browser_cmd '$url'" > /dev/null 2>&1 &
    else
        $browser_cmd "$url" > /dev/null 2>&1 &
    fi

    print_info "Browser opened successfully"
}

# Run server and open browser after deployment
run_after_deploy() {
    echo ""
    print_info "========================================="
    print_info "Starting post-deployment services..."
    print_info "========================================="

    # Start server if server was deployed
    if [ "$DEPLOY_MODE" = "all" ] || [ "$DEPLOY_MODE" = "server" ]; then
        start_server
    fi

    # Open browser if client was deployed
    if [ "$DEPLOY_MODE" = "all" ] || [ "$DEPLOY_MODE" = "client" ]; then
        # Wait a moment for server to be ready
        sleep 2
        open_browser
    fi

    echo ""
    print_info "Post-deployment services started"
}

# Deploy web client
deploy_client() {
    print_info "========================================="
    print_info "Starting web client deployment..."
    print_info "========================================="

    # 1. Pre-check
    check_webclient

    # 2. Install Nginx and modify main config
    install_nginx
    modify_nginx_main_config

    # 3. Deploy files and configure
    deploy_files
    configure_server_config
    configure_nginx

    # 4. Reload Nginx to apply configuration
    reload_nginx

    print_info "Web client deployment completed"
}

# Main function
main() {
    # Parse command line arguments
    parse_args "$@"

    print_info "Starting HandDriver Web deployment..."
    echo ""

    check_root
    check_ubuntu

    # Show deployment mode menu (Quick or Custom)
    show_deploy_menu

    # Get configuration (skipped in quick deploy mode)
    if [ "$QUICK_DEPLOY" != true ]; then
        get_user_config
    fi

    # Execute deployment based on mode
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

    # Run server and open browser after deployment
    if [ "$RUN_AFTER_DEPLOY" = true ]; then
        run_after_deploy
    elif [ "$AUTO_YES" = false ]; then
        printf 'Start server and open browser now? (Y/n): ' && read run_now
        if [ "$run_now" != "n" ] && [ "$run_now" != "N" ]; then
            run_after_deploy
        fi
    fi
}

# Execute main function
main "$@"
