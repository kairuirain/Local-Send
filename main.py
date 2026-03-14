#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
局域网文件分享中心
运行在8080端口，支持文件上传和下载
"""

import os
import socket
import logging
import unicodedata
import urllib.parse
import hashlib
import json
import random
from datetime import datetime
from flask import Flask, render_template_string, request, send_file, jsonify
from werkzeug.exceptions import RequestEntityTooLarge

# ==================== 用户管理模块 ====================

class UserManager:
    """用户管理器，基于浏览器指纹识别用户"""

    def __init__(self, user_data_dir='users'):
        self.user_data_dir = user_data_dir
        os.makedirs(user_data_dir, exist_ok=True)
        self.chinese_chars = [
            '一', '二', '三', '四', '五', '六', '七', '八', '九', '十',
            '天', '地', '玄', '黄', '宇', '宙', '洪', '荒',
            '春', '夏', '秋', '冬', '东', '南', '西', '北',
            '梅', '兰', '竹', '菊', '松', '柏', '桃', '李',
            '云', '风', '雨', '雪', '霜', '露', '霞', '雾',
            '山', '水', '林', '河', '海', '江', '湖', '溪',
            '星', '月', '日', '光', '辉', '明', '亮', '清',
            '金', '银', '铜', '铁', '玉', '石', '珠', '宝',
            '龙', '凤', '麒', '麟', '鹤', '鸟', '鱼', '马',
            '心', '灵', '智', '慧', '勇', '毅', '仁', '义'
        ]

    def _generate_fingerprint(self, request_obj):
        """生成浏览器指纹"""
        fingerprint_data = [
            request_obj.headers.get('User-Agent', ''),
            request_obj.headers.get('Accept-Language', ''),
            request_obj.headers.get('Accept-Encoding', ''),
            request_obj.remote_addr or ''
        ]
        fingerprint_str = '|'.join(fingerprint_data)
        return hashlib.sha256(fingerprint_str.encode('utf-8')).hexdigest()

    def _generate_chinese_username(self, length=8):
        """生成8个字符的中文名字"""
        return ''.join(random.choices(self.chinese_chars, k=length))

    def get_or_create_user(self, request_obj):
        """获取或创建用户"""
        fingerprint = self._generate_fingerprint(request_obj)
        user_file = os.path.join(self.user_data_dir, f"{fingerprint}.json")

        if os.path.exists(user_file):
            with open(user_file, 'r', encoding='utf-8') as f:
                user_data = json.load(f)
        else:
            # 创建新用户
            username = self._generate_chinese_username(8)

            user_data = {
                'fingerprint': fingerprint,
                'user_id': fingerprint[:16],  # 使用指纹前16位作为用户ID
                'username': username,
                'created_at': datetime.now().isoformat(),
                'last_visit': datetime.now().isoformat()
            }

            with open(user_file, 'w', encoding='utf-8') as f:
                json.dump(user_data, f, ensure_ascii=False, indent=2)

            # 创建用户个人文件目录
            user_folder = os.path.join('user_files', user_data['user_id'])
            os.makedirs(user_folder, exist_ok=True)

            logging.info(f"新用户创建: {username} (ID: {user_data['user_id']})")

        # 更新最后访问时间
        user_data['last_visit'] = datetime.now().isoformat()
        with open(user_file, 'w', encoding='utf-8') as f:
            json.dump(user_data, f, ensure_ascii=False, indent=2)

        return user_data

    def get_user_by_id(self, user_id):
        """根据用户ID获取用户信息"""
        for filename in os.listdir(self.user_data_dir):
            if filename.endswith('.json'):
                user_file = os.path.join(self.user_data_dir, filename)
                try:
                    with open(user_file, 'r', encoding='utf-8') as f:
                        user_data = json.load(f)
                    if user_data.get('user_id') == user_id:
                        return user_data
                except Exception:
                    continue
        return None

# ==================== 文件管理模块 ====================

class FileManager:
    """文件管理器，处理个人文件和公共文件"""

    def __init__(self):
        self.public_folder = 'public'
        self.user_base_folder = 'user_files'
        os.makedirs(self.public_folder, exist_ok=True)
        os.makedirs(self.user_base_folder, exist_ok=True)

    def get_user_folder(self, user_id):
        """获取用户文件目录"""
        folder = os.path.join(self.user_base_folder, user_id)
        os.makedirs(folder, exist_ok=True)
        return folder

    def add_file_metadata(self, file_path, uploader_id, uploader_name, is_public=False):
        """添加文件元数据"""
        metadata_file = os.path.join(os.path.dirname(file_path), '.metadata.json')

        metadata = {}
        if os.path.exists(metadata_file):
            with open(metadata_file, 'r', encoding='utf-8') as f:
                metadata = json.load(f)

        file_key = os.path.basename(file_path)
        metadata[file_key] = {
            'uploader_id': uploader_id,
            'uploader_name': uploader_name,
            'upload_time': datetime.now().isoformat(),
            'is_public': is_public
        }

        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

    def get_file_metadata(self, file_path):
        """获取文件元数据"""
        metadata_file = os.path.join(os.path.dirname(file_path), '.metadata.json')
        if not os.path.exists(metadata_file):
            return None

        try:
            with open(metadata_file, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            return metadata.get(os.path.basename(file_path))
        except Exception:
            return None

    def can_access_file(self, file_path, user_id):
        """检查用户是否有权限访问文件"""
        metadata = self.get_file_metadata(file_path)
        if not metadata:
            # 如果没有元数据，默认不允许访问私有文件
            return False

        # 如果是公共文件，所有人都可以访问
        if metadata.get('is_public', False):
            return True

        # 如果是私有文件，只有上传者可以访问
        return metadata.get('uploader_id') == user_id

    def get_files_list(self, folder, include_metadata=True):
        """获取文件列表"""
        files = []
        try:
            for filename in os.listdir(folder):
                if filename.startswith('.'):
                    continue

                file_path = os.path.join(folder, filename)
                if os.path.isfile(file_path):
                    file_size = os.path.getsize(file_path)
                    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''

                    file_info = {
                        'name': filename,
                        'size': file_size,
                        'formatted_size': self._format_file_size(file_size),
                        'modified': datetime.fromtimestamp(os.path.getmtime(file_path)).strftime('%Y-%m-%d %H:%M:%S'),
                        'ext': ext
                    }

                    if include_metadata:
                        metadata = self.get_file_metadata(file_path)
                        if metadata:
                            file_info['uploader_name'] = metadata.get('uploader_name', '未知')
                            file_info['upload_time'] = metadata.get('upload_time', '')
                        else:
                            file_info['uploader_name'] = '未知'

                    files.append(file_info)

            files.sort(key=lambda x: os.path.getmtime(os.path.join(folder, x['name'])), reverse=True)
        except Exception as e:
            logger.error(f"读取文件列表失败: {e}")
            raise
        return files

    def _format_file_size(self, size):
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.2f} {unit}"
            size /= 1024
        return f"{size:.2f} TB"

# ==================== 配置 ====================

UPLOAD_FOLDER = 'files'  # 兼容旧版本
MAX_FILE_SIZE = 5000 * 1024 * 1024  # 5000MB
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'zip', 'rar', '7z', 'mp3', 'mp4', 'avi', 'mov', 'py', 'js', 'html', 'css', 'json', 'xml', 'md'}
HOST = '0.0.0.0'
PORT = 8080

# 创建Flask应用
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

# 初始化管理器
user_manager = UserManager()
file_manager = FileManager()

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('file_share.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 确保目录存在
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    """检查文件扩展名是否允许"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def safe_filename(filename):
    """处理文件名，保留中文字符"""
    # 解码URL编码的文件名
    filename = urllib.parse.unquote(filename)
    # 规范化Unicode字符
    filename = unicodedata.normalize('NFC', filename)
    # 移除控制字符
    filename = ''.join(char for char in filename if unicodedata.category(char)[0] != 'C' or char in '\t\n\r')
    # 替换路径分隔符
    filename = filename.replace('/', '_').replace('\\', '_')
    # 移除首尾空格和点
    filename = filename.strip(' .')
    # 如果文件名为空，使用默认名称
    if not filename:
        filename = 'unnamed_file'
    return filename

def get_local_ip():
    """获取本地IP地址"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def get_current_user():
    """获取当前用户"""
    try:
        return user_manager.get_or_create_user(request)
    except Exception as e:
        logger.error(f"获取用户信息失败: {e}")
        return None

@app.route('/')
def index():
    """主页 - 显示公共文件列表"""
    try:
        files = file_manager.get_files_list(file_manager.public_folder, include_metadata=True)
    except Exception:
        files = []

    user = get_current_user()
    return render_template_string(
        HTML_TEMPLATE,
        files=files,
        local_ip=get_local_ip(),
        port=PORT,
        current_user=user,
        view='public'
    )

@app.route('/my-files')
def my_files():
    """个人文件页面"""
    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'message': '用户未登录'}), 401

    try:
        user_folder = file_manager.get_user_folder(user['user_id'])
        files = file_manager.get_files_list(user_folder, include_metadata=True)
    except Exception:
        files = []

    return render_template_string(
        HTML_TEMPLATE,
        files=files,
        local_ip=get_local_ip(),
        port=PORT,
        current_user=user,
        view='private'
    )

@app.route('/api/files')
def api_files():
    """API: 获取公共文件列表"""
    try:
        files = file_manager.get_files_list(file_manager.public_folder, include_metadata=True)
        total_size = sum(f['size'] for f in files)
        return jsonify({
            'success': True,
            'files': files,
            'stats': {
                'total_files': len(files),
                'total_size': file_manager._format_file_size(total_size)
            }
        })
    except Exception as e:
        logger.error(f"获取文件列表失败: {e}")
        return jsonify({'success': False, 'message': '获取文件列表失败'}), 500

@app.route('/api/my-files')
def api_my_files():
    """API: 获取个人文件列表"""
    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'message': '用户未登录'}), 401

    try:
        user_folder = file_manager.get_user_folder(user['user_id'])
        files = file_manager.get_files_list(user_folder, include_metadata=True)
        total_size = sum(f['size'] for f in files)
        return jsonify({
            'success': True,
            'files': files,
            'stats': {
                'total_files': len(files),
                'total_size': file_manager._format_file_size(total_size)
            }
        })
    except Exception as e:
        logger.error(f"获取个人文件列表失败: {e}")
        return jsonify({'success': False, 'message': '获取文件列表失败'}), 500

@app.route('/api/user/info')
def api_user_info():
    """API: 获取当前用户信息"""
    try:
        user = get_current_user()
        if user:
            return jsonify({
                'success': True,
                'user': {
                    'user_id': user.get('user_id'),
                    'username': user.get('username'),
                    'created_at': user.get('created_at')
                }
            })
        return jsonify({'success': False, 'message': '获取用户信息失败'}), 500
    except Exception as e:
        logger.error(f"获取用户信息失败: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/config')
def api_config():
    """API: 获取服务器配置"""
    try:
        return jsonify({
            'success': True,
            'config': {
                'max_file_size_mb': MAX_FILE_SIZE // 1024 // 1024,
                'allowed_extensions': list(ALLOWED_EXTENSIONS),
                'server_version': '2.0.0'
            }
        })
    except Exception as e:
        logger.error(f"获取配置失败: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/batch-delete', methods=['POST'])
def batch_delete_files():
    """批量删除文件"""
    try:
        data = request.get_json()
        filenames = data.get('files', [])
        
        if not filenames:
            return jsonify({'success': False, 'message': '未选择文件'}), 400
        
        deleted_count = 0
        failed_files = []
        
        for filename in filenames:
            try:
                # URL解码文件名
                decoded_filename = urllib.parse.unquote(filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], decoded_filename)
                
                # 安全检查
                real_file_path = os.path.realpath(file_path)
                real_upload_folder = os.path.realpath(app.config['UPLOAD_FOLDER'])
                if not real_file_path.startswith(real_upload_folder):
                    failed_files.append(filename)
                    continue
                
                if os.path.exists(file_path):
                    os.remove(file_path)
                    deleted_count += 1
                    logger.info(f"文件删除成功: {decoded_filename}")
                else:
                    failed_files.append(filename)
            except Exception as e:
                logger.error(f"删除文件失败 {filename}: {e}")
                failed_files.append(filename)
        
        if failed_files:
            return jsonify({
                'success': True,
                'message': f'成功删除 {deleted_count} 个文件，{len(failed_files)} 个文件删除失败',
                'deleted_count': deleted_count,
                'failed_files': failed_files
            })
        else:
            return jsonify({
                'success': True,
                'message': f'成功删除 {deleted_count} 个文件',
                'deleted_count': deleted_count
            })
    except Exception as e:
        logger.error(f"批量删除失败: {e}")
        return jsonify({'success': False, 'message': f'批量删除失败: {str(e)}'}), 500

@app.route('/upload', methods=['POST'])
def upload_file():
    """处理文件上传（默认上传到公共目录）"""
    return _upload_file_internal(public=True)

@app.route('/upload/private', methods=['POST'])
def upload_private_file():
    """处理私有文件上传"""
    return _upload_file_internal(public=False)

def _upload_file_internal(public=True):
    """内部文件上传处理"""
    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'message': '用户未登录'}), 401

    if 'file' not in request.files:
        logger.warning("上传请求中没有文件")
        return jsonify({'success': False, 'message': '没有选择文件'}), 400

    file = request.files['file']
    if file.filename == '':
        logger.warning("上传的文件名为空")
        return jsonify({'success': False, 'message': '没有选择文件'}), 400

    if file and allowed_file(file.filename):
        filename = safe_filename(file.filename)

        # 选择上传目录
        if public:
            upload_folder = file_manager.public_folder
        else:
            upload_folder = file_manager.get_user_folder(user['user_id'])

        file_path = os.path.join(upload_folder, filename)

        # 如果文件已存在，添加数字后缀
        counter = 1
        original_filename = filename
        while os.path.exists(file_path):
            name, ext = os.path.splitext(original_filename)
            filename = f"{name}_{counter}{ext}"
            file_path = os.path.join(upload_folder, filename)
            counter += 1

        try:
            file.save(file_path)
            logger.info(f"文件上传成功: {filename} (用户: {user['username']}, 公共: {public})")

            # 添加文件元数据
            file_manager.add_file_metadata(
                file_path,
                user['user_id'],
                user['username'],
                is_public=public
            )

            return jsonify({
                'success': True,
                'message': f'文件 "{filename}" 上传成功！',
                'filename': filename,
                'is_public': public
            })
        except Exception as e:
            logger.error(f"文件上传失败: {e}")
            return jsonify({'success': False, 'message': f'上传失败: {str(e)}'}), 500
    else:
        logger.warning(f"不允许的文件类型: {file.filename}")
        return jsonify({'success': False, 'message': '不允许的文件类型'}), 400

@app.route('/view/<path:filename>')
def view_file(filename):
    """处理公共文件预览（浏览器直接显示）"""
    return _view_file_internal(filename, public=True)

@app.route('/view/private/<path:filename>')
def view_private_file(filename):
    """处理私有文件预览（浏览器直接显示）"""
    return _view_file_internal(filename, public=False)

@app.route('/download/<path:filename>')
def download_file(filename):
    """处理公共文件下载"""
    return _download_file_internal(filename, public=True)

@app.route('/download/private/<path:filename>')
def download_private_file(filename):
    """处理私有文件下载"""
    return _download_file_internal(filename, public=False)

def _view_file_internal(filename, public=True):
    """内部文件预览处理（浏览器直接显示，不下载）"""
    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'message': '用户未登录'}), 401

    try:
        # URL解码文件名
        filename = urllib.parse.unquote(filename)

        # 选择目录
        if public:
            view_folder = file_manager.public_folder
        else:
            view_folder = file_manager.get_user_folder(user['user_id'])

        file_path = os.path.join(view_folder, filename)

        # 安全检查
        real_file_path = os.path.realpath(file_path)
        real_view_folder = os.path.realpath(view_folder)
        if not real_file_path.startswith(real_view_folder):
            logger.warning(f"非法文件路径: {filename} (用户: {user['username']})")
            return jsonify({'success': False, 'message': '非法文件路径'}), 403

        if not os.path.exists(file_path):
            # 如果公共文件不存在，尝试在用户私有目录中查找
            if public:
                user_folder = file_manager.get_user_folder(user['user_id'])
                private_file_path = os.path.join(user_folder, filename)
                if os.path.exists(private_file_path):
                    # 检查用户是否有权限访问这个私有文件
                    if not file_manager.can_access_file(private_file_path, user['user_id']):
                        logger.warning(f"无权限访问私有文件: {filename} (用户: {user['username']})")
                        return jsonify({'success': False, 'message': '无权限访问此文件'}), 403
                    logger.info(f"公共文件不存在，重定向到私有文件: {filename} (用户: {user['username']})")
                    file_path = private_file_path
                    view_folder = user_folder
                else:
                    logger.warning(f"预览的文件不存在: {filename} (用户: {user['username']})")
                    return jsonify({'success': False, 'message': '文件不存在'}), 404
            else:
                # 如果私有文件不存在，尝试在公共目录中查找
                public_file_path = os.path.join(file_manager.public_folder, filename)
                if os.path.exists(public_file_path):
                    logger.info(f"私有文件不存在，重定向到公共文件: {filename} (用户: {user['username']})")
                    file_path = public_file_path
                    view_folder = file_manager.public_folder
                else:
                    logger.warning(f"预览的文件不存在: {filename} (用户: {user['username']})")
                    return jsonify({'success': False, 'message': '文件不存在'}), 404
        else:
            # 文件存在，检查权限
            if not public:
                # 私有文件，检查用户是否有权限
                if not file_manager.can_access_file(file_path, user['user_id']):
                    logger.warning(f"无权限访问私有文件: {filename} (用户: {user['username']})")
                    return jsonify({'success': False, 'message': '无权限访问此文件'}), 403

        logger.info(f"文件预览: {filename} (用户: {user['username']}, 公共: {public})")

        # 使用 inline 方式让浏览器直接显示
        return send_file(file_path, as_attachment=False)
    except Exception as e:
        logger.error(f"文件预览失败: {e}")
        return jsonify({'success': False, 'message': f'预览失败: {str(e)}'}), 500

def _download_file_internal(filename, public=True):
    """内部文件下载处理"""
    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'message': '用户未登录'}), 401

    try:
        # URL解码文件名
        filename = urllib.parse.unquote(filename)

        # 选择目录
        if public:
            download_folder = file_manager.public_folder
        else:
            download_folder = file_manager.get_user_folder(user['user_id'])

        file_path = os.path.join(download_folder, filename)

        # 安全检查
        real_file_path = os.path.realpath(file_path)
        real_download_folder = os.path.realpath(download_folder)
        if not real_file_path.startswith(real_download_folder):
            logger.warning(f"非法文件路径: {filename} (用户: {user['username']})")
            return jsonify({'success': False, 'message': '非法文件路径'}), 403

        if not os.path.exists(file_path):
            # 如果公共文件不存在，尝试在用户私有目录中查找
            if public:
                user_folder = file_manager.get_user_folder(user['user_id'])
                private_file_path = os.path.join(user_folder, filename)
                if os.path.exists(private_file_path):
                    # 检查用户是否有权限访问这个私有文件
                    if not file_manager.can_access_file(private_file_path, user['user_id']):
                        logger.warning(f"无权限访问私有文件: {filename} (用户: {user['username']})")
                        return jsonify({'success': False, 'message': '无权限访问此文件'}), 403
                    logger.info(f"公共文件不存在，重定向到私有文件: {filename} (用户: {user['username']})")
                    file_path = private_file_path
                    download_folder = user_folder
                else:
                    logger.warning(f"下载的文件不存在: {filename} (用户: {user['username']})")
                    return jsonify({'success': False, 'message': '文件不存在'}), 404
            else:
                # 如果私有文件不存在，尝试在公共目录中查找
                public_file_path = os.path.join(file_manager.public_folder, filename)
                if os.path.exists(public_file_path):
                    logger.info(f"私有文件不存在，重定向到公共文件: {filename} (用户: {user['username']})")
                    file_path = public_file_path
                    download_folder = file_manager.public_folder
                else:
                    logger.warning(f"下载的文件不存在: {filename} (用户: {user['username']})")
                    return jsonify({'success': False, 'message': '文件不存在'}), 404
        else:
            # 文件存在，检查权限
            if not public:
                # 私有文件，检查用户是否有权限
                if not file_manager.can_access_file(file_path, user['user_id']):
                    logger.warning(f"无权限访问私有文件: {filename} (用户: {user['username']})")
                    return jsonify({'success': False, 'message': '无权限访问此文件'}), 403

        logger.info(f"文件下载: {filename} (用户: {user['username']}, 公共: {public})")

        # 对下载文件名进行URL编码以支持中文
        encoded_filename = urllib.parse.quote(filename)
        response = send_file(file_path, as_attachment=True)
        response.headers['Content-Disposition'] = f"attachment; filename*=UTF-8''{encoded_filename}"
        return response
    except Exception as e:
        logger.error(f"文件下载失败: {e}")
        return jsonify({'success': False, 'message': f'下载失败: {str(e)}'}), 500

@app.route('/delete/<path:filename>', methods=['POST'])
def delete_file(filename):
    """删除公共文件"""
    return _delete_file_internal(filename, public=True)

@app.route('/delete/private/<path:filename>', methods=['POST'])
def delete_private_file(filename):
    """删除私有文件"""
    return _delete_file_internal(filename, public=False)

def _delete_file_internal(filename, public=True):
    """内部文件删除处理"""
    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'message': '用户未登录'}), 401

    try:
        # URL解码文件名
        filename = urllib.parse.unquote(filename)

        # 选择目录
        if public:
            delete_folder = file_manager.public_folder
        else:
            delete_folder = file_manager.get_user_folder(user['user_id'])

        file_path = os.path.join(delete_folder, filename)

        # 安全检查
        real_file_path = os.path.realpath(file_path)
        real_delete_folder = os.path.realpath(delete_folder)
        if not real_file_path.startswith(real_delete_folder):
            logger.warning(f"非法文件路径: {filename} (用户: {user['username']})")
            return jsonify({'success': False, 'message': '非法文件路径'}), 403

        if not os.path.exists(file_path):
            return jsonify({'success': False, 'message': '文件不存在'}), 404

        os.remove(file_path)
        logger.info(f"文件删除成功: {filename} (用户: {user['username']}, 公共: {public})")
        return jsonify({'success': True, 'message': f'文件 "{filename}" 已删除'})
    except Exception as e:
        logger.error(f"文件删除失败: {e}")
        return jsonify({'success': False, 'message': f'删除失败: {str(e)}'}), 500

@app.errorhandler(RequestEntityTooLarge)
def handle_large_file(e):
    """处理文件过大的错误"""
    logger.warning("上传的文件超过大小限制")
    return jsonify({'success': False, 'message': f'文件大小超过限制（最大{MAX_FILE_SIZE//1024//1024}MB）'}), 413

@app.errorhandler(Exception)
def handle_exception(e):
    """全局错误处理"""
    logger.error(f"服务器错误: {e}", exc_info=True)
    return jsonify({'success': False, 'message': '服务器内部错误'}), 500

@app.errorhandler(404)
def handle_404(e):
    """处理404错误"""
    path = request.path
    logger.warning(f"404错误 - 请求路径不存在: {path} - User-Agent: {request.headers.get('User-Agent', 'unknown')}")
    return jsonify({'success': False, 'message': '请求的资源不存在'}), 404

# HTML模板 - 简洁现代化UI设计
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>文件传输中心</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        :root {
            --primary: #2196F3;
            --primary-dark: #1976D2;
            --success: #4CAF50;
            --danger: #f44336;
            --bg: #f5f7fa;
            --card-bg: #ffffff;
            --text: #333333;
            --text-secondary: #666666;
            --border: #e0e0e0;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'PingFang SC', 'Microsoft YaHei', sans-serif;
            background: var(--bg);
            min-height: 100vh;
            color: var(--text);
            line-height: 1.6;
        }
        
        .container {
            max-width: 900px;
            margin: 0 auto;
            padding: 40px 20px;
        }
        
        /* 头部 */
        .header {
            text-align: center;
            margin-bottom: 40px;
        }
        
        .header h1 {
            font-size: 28px;
            font-weight: 600;
            color: var(--text);
            margin-bottom: 8px;
        }
        
        .header p {
            color: var(--text-secondary);
            font-size: 14px;
        }
        
        .server-info {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            background: var(--card-bg);
            padding: 10px 20px;
            border-radius: 20px;
            font-size: 13px;
            color: var(--text-secondary);
            margin-top: 15px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        }
        
        .server-info strong {
            color: var(--primary);
            font-weight: 500;
        }

        /* 用户信息 */
        .user-info {
            display: inline-flex;
            align-items: center;
            gap: 12px;
            background: var(--card-bg);
            padding: 10px 20px;
            border-radius: 20px;
            font-size: 14px;
            color: var(--text);
            margin-top: 15px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        }

        .user-info svg {
            color: var(--primary);
        }

        .user-info #username {
            font-weight: 600;
            color: var(--primary);
        }

        /* 导航标签 */
        .nav-tabs {
            display: flex;
            justify-content: center;
            gap: 12px;
            margin: 30px 0;
        }

        .nav-tab {
            padding: 10px 24px;
            border-radius: 20px;
            font-size: 14px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
            background: var(--card-bg);
            color: var(--text-secondary);
            border: 1px solid var(--border);
        }

        .nav-tab:hover {
            border-color: var(--primary);
            color: var(--primary);
        }

        .nav-tab.active {
            background: var(--primary);
            color: white;
            border-color: var(--primary);
        }

        /* 卡片 */
        .card {
            background: var(--card-bg);
            border-radius: 12px;
            padding: 32px;
            margin-bottom: 24px;
            box-shadow: 0 2px 12px rgba(0,0,0,0.06);
        }
        
        /* 上传区域 */
        .upload-zone {
            border: 2px dashed var(--border);
            border-radius: 10px;
            padding: 48px 32px;
            text-align: center;
            cursor: pointer;
            transition: all 0.25s ease;
            background: #fafbfc;
        }
        
        .upload-zone:hover {
            border-color: var(--primary);
            background: #f0f7ff;
        }
        
        .upload-zone.dragover {
            border-color: var(--primary);
            background: #e3f2fd;
            border-style: solid;
        }
        
        .upload-icon {
            width: 64px;
            height: 64px;
            margin: 0 auto 16px;
            background: var(--primary);
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        
        .upload-icon svg {
            width: 28px;
            height: 28px;
            fill: white;
        }
        
        .upload-title {
            font-size: 16px;
            font-weight: 500;
            color: var(--text);
            margin-bottom: 6px;
        }
        
        .upload-hint {
            font-size: 13px;
            color: var(--text-secondary);
        }
        
        #file-input {
            display: none;
        }
        
        /* 进度条 */
        .progress-wrap {
            display: none;
            margin-top: 24px;
        }
        
        .progress-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
            font-size: 13px;
        }
        
        .progress-file {
            color: var(--text);
            font-weight: 500;
        }
        
        .progress-percent {
            color: var(--primary);
            font-weight: 600;
        }
        
        .progress-bar {
            height: 6px;
            background: #e8e8e8;
            border-radius: 3px;
            overflow: hidden;
        }
        
        .progress-fill {
            height: 100%;
            background: var(--primary);
            width: 0%;
            transition: width 0.2s ease;
            border-radius: 3px;
        }
        
        /* 文件列表 */
        .section-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 12px;
            border-bottom: 1px solid var(--border);
        }
        
        .section-title {
            font-size: 16px;
            font-weight: 600;
            color: var(--text);
        }
        
        .btn-refresh {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 8px 16px;
            background: transparent;
            border: 1px solid var(--border);
            border-radius: 6px;
            font-size: 13px;
            font-weight: 500;
            color: var(--text-secondary);
            cursor: pointer;
            transition: all 0.2s;
        }
        
        .btn-refresh:hover {
            background: #f5f5f5;
            border-color: var(--primary);
            color: var(--primary);
        }
        
        .btn-refresh:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }
        
        .btn-refresh svg {
            width: 14px;
            height: 14px;
            fill: currentColor;
            transition: transform 0.5s ease;
        }
        
        .btn-refresh.loading svg {
            animation: spin 1s linear infinite;
        }
        
        @keyframes spin {
            from { transform: rotate(0deg); }
            to { transform: rotate(360deg); }
        }
        
        .file-list-loading {
            text-align: center;
            padding: 40px;
            color: var(--text-secondary);
        }
        
        .file-list-loading svg {
            width: 32px;
            height: 32px;
            fill: var(--primary);
            animation: spin 1s linear infinite;
        }
        
        .file-count {
            font-weight: 400;
            color: var(--text-secondary);
            font-size: 14px;
            margin-left: 6px;
        }
        
        .file-list {
            display: flex;
            flex-direction: column;
            gap: 12px;
        }
        
        .file-item {
            display: flex;
            align-items: center;
            padding: 16px;
            background: #fafbfc;
            border-radius: 8px;
            border: 1px solid transparent;
            transition: all 0.2s ease;
            cursor: pointer;
        }

        .file-item:hover {
            background: #f0f7ff;
            border-color: #bbdefb;
        }
        
        .file-thumb {
            width: 40px;
            height: 40px;
            background: white;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            margin-right: 16px;
            flex-shrink: 0;
            box-shadow: 0 1px 3px rgba(0,0,0,0.08);
        }
        
        .file-thumb svg {
            width: 20px;
            height: 20px;
            fill: var(--primary);
        }
        
        .file-info {
            flex: 1;
            min-width: 0;
        }

        .file-name {
            font-size: 14px;
            font-weight: 500;
            color: var(--text);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            margin-bottom: 2px;
        }

        .file-meta {
            font-size: 12px;
            color: var(--text-secondary);
            display: flex;
            gap: 12px;
            align-items: center;
        }

        .file-uploader {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            color: var(--primary);
            font-weight: 500;
            background: #e3f2fd;
            padding: 2px 8px;
            border-radius: 4px;
        }

        .file-uploader svg {
            width: 12px;
            height: 12px;
            fill: currentColor;
        }

        .file-actions {
            display: flex;
            gap: 8px;
            flex-shrink: 0;
        }
        
        .btn {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            padding: 8px 14px;
            border-radius: 6px;
            font-size: 13px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
            border: none;
            text-decoration: none;
        }
        
        .btn-primary {
            background: var(--primary);
            color: white;
        }
        
        .btn-primary:hover {
            background: var(--primary-dark);
        }
        
        .btn-danger {
            background: transparent;
            color: var(--danger);
            border: 1px solid #ffcdd2;
        }
        
        .btn-danger:hover {
            background: #ffebee;
        }
        
        .btn svg {
            width: 14px;
            height: 14px;
            fill: currentColor;
        }
        
        /* 空状态 */
        .empty-state {
            text-align: center;
            padding: 48px 20px;
            color: var(--text-secondary);
        }
        
        .empty-icon {
            width: 80px;
            height: 80px;
            margin: 0 auto 16px;
            background: #f0f0f0;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        
        .empty-icon svg {
            width: 36px;
            height: 36px;
            fill: #bbb;
        }
        
        .empty-text {
            font-size: 14px;
        }
        
        /* 提示消息 */
        .toast {
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 14px 20px;
            border-radius: 8px;
            color: white;
            font-size: 14px;
            font-weight: 500;
            z-index: 1000;
            animation: slideIn 0.3s ease;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .toast.success {
            background: var(--success);
        }
        
        .toast.error {
            background: var(--danger);
        }
        
        @keyframes slideIn {
            from {
                transform: translateX(100px);
                opacity: 0;
            }
            to {
                transform: translateX(0);
                opacity: 1;
            }
        }
        
        /* 响应式 */
        @media (max-width: 640px) {
            .container {
                padding: 20px 16px;
            }
            
            .card {
                padding: 20px;
            }
            
            .upload-zone {
                padding: 32px 20px;
            }
            
            .file-item {
                flex-wrap: wrap;
                gap: 12px;
            }
            
            .file-actions {
                width: 100%;
                justify-content: flex-end;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- 头部 -->
        <div class="header">
            <h1>文件传输中心</h1>
            <p>局域网内快速安全地分享文件</p>
            <div class="server-info">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="12" cy="12" r="10"/>
                    <line x1="2" y1="12" x2="22" y2="12"/>
                    <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
                </svg>
                <span>http://{{ local_ip }}:{{ port|default(8080) }}</span>
            </div>
            {% if current_user %}
            <div class="user-info">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/>
                </svg>
                <span id="username">{{ current_user.username }}</span>
            </div>
            {% endif %}
        </div>

        <!-- 导航标签 -->
        <div class="nav-tabs">
            <button class="nav-tab {% if view == 'public' %}active{% endif %}" onclick="switchView('public')">
                公共文件
            </button>
            <button class="nav-tab {% if view == 'private' %}active{% endif %}" onclick="switchView('private')">
                我的文件
            </button>
        </div>
        
        <!-- 上传区域 -->
        <div class="card">
            <div class="upload-zone" id="upload-zone">
                <div class="upload-icon">
                    <svg viewBox="0 0 24 24"><path d="M9 16h6v-6h4l-7-7-7 7h4v6zm-4 2h14v2H5v-2z"/></svg>
                </div>
                <div class="upload-title">点击或拖拽文件到此处上传</div>
                <div class="upload-hint">支持多种文件格式，单个文件最大 5000MB</div>
                <input type="file" id="file-input" multiple>
            </div>
            
            <div class="progress-wrap" id="progress-wrap">
                <div class="progress-header">
                    <span class="progress-file" id="progress-file">准备上传...</span>
                    <span class="progress-percent" id="progress-percent">0%</span>
                </div>
                <div class="progress-bar">
                    <div class="progress-fill" id="progress-fill"></div>
                </div>
            </div>
        </div>
        
        <!-- 文件列表 -->
        <div class="card">
            <div class="section-header">
                <div class="section-title">
                    文件列表<span class="file-count" id="file-count">({{ files|length }})</span>
                </div>
                <button class="btn-refresh" id="btn-refresh" onclick="refreshFileList()">
                    <svg viewBox="0 0 24 24"><path d="M17.65 6.35C16.2 4.9 14.21 4 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08c-.82 2.33-3.04 4-5.65 4-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"/></svg>
                    刷新
                </button>
            </div>
            <div class="file-list-loading" id="file-list-loading" style="display: none;">
                <svg viewBox="0 0 24 24"><path d="M12 4V1L8 5l4 4V6c3.31 0 6 2.69 6 6 0 1.01-.25 1.97-.7 2.8l1.46 1.46C19.54 15.03 20 13.57 20 12c0-4.42-3.58-8-8-8zm0 14c-3.31 0-6-2.69-6-6 0-1.01.25-1.97.7-2.8L5.24 7.74C4.46 8.97 4 10.43 4 12c0 4.42 3.58 8 8 8v3l4-4-4-4v3z"/></svg>
                <p style="margin-top: 12px; font-size: 14px;">加载中...</p>
            </div>
            
            <div class="file-list" id="file-list">
            {% if files %}
                {% for file in files %}
                <div class="file-item" onclick="openFile('{{ file.name | urlencode }}', '{{ view }}')">
                    <div class="file-thumb">
                        <svg viewBox="0 0 24 24"><path d="M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z"/></svg>
                    </div>
                    <div class="file-info">
                        <div class="file-name">{{ file.name }}</div>
                        <div class="file-meta">
                            <span>{{ file.formatted_size }} · {{ file.modified }}</span>
                            {% if file.uploader_name %}
                            <span class="file-uploader">
                                <svg viewBox="0 0 24 24"><path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/></svg>
                                {{ file.uploader_name }}
                            </span>
                            {% endif %}
                        </div>
                    </div>
                    <div class="file-actions">
                        <a href="/download/{{ file.name | urlencode }}" class="btn btn-primary" onclick="event.stopPropagation()">
                            <svg viewBox="0 0 24 24"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/></svg>
                            下载
                        </a>
                        <button class="btn btn-danger" onclick="event.stopPropagation(); deleteFile('{{ file.name | urlencode }}')">
                            <svg viewBox="0 0 24 24"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg>
                            删除
                        </button>
                    </div>
                </div>
                {% endfor %}
            </div>
            {% else %}
            <div class="empty-state">
                <div class="empty-icon">
                    <svg viewBox="0 0 24 24"><path d="M20 6h-8l-2-2H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2zm0 12H4V8h16v10z"/></svg>
                </div>
                <div class="empty-text">暂无文件，请上传第一个文件</div>
            </div>
            {% endif %}
            </div>
        </div>
    </div>

    <script>
        const uploadZone = document.getElementById('upload-zone');
        const fileInput = document.getElementById('file-input');
        const progressWrap = document.getElementById('progress-wrap');
        const progressFill = document.getElementById('progress-fill');
        const progressFile = document.getElementById('progress-file');
        const progressPercent = document.getElementById('progress-percent');

        let currentView = '{{ view|default("public") }}';

        // 切换视图
        uploadZone.addEventListener('click', () => fileInput.click());
        
        // 拖拽事件
        uploadZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            uploadZone.classList.add('dragover');
        });
        
        uploadZone.addEventListener('dragleave', () => {
            uploadZone.classList.remove('dragover');
        });
        
        uploadZone.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadZone.classList.remove('dragover');
            [...e.dataTransfer.files].forEach(uploadFile);
        });
        
        // 文件选择
        fileInput.addEventListener('change', () => {
            [...fileInput.files].forEach(uploadFile);
            fileInput.value = '';
        });

        // 切换视图
        function switchView(view) {
            if (view === 'public') {
                window.location.href = '/';
            } else if (view === 'private') {
                window.location.href = '/my-files';
            }
        }

        // 上传文件
        function uploadFile(file) {
            progressWrap.style.display = 'block';
            progressFill.style.width = '0%';
            progressFile.textContent = file.name;
            progressPercent.textContent = '0%';

            const formData = new FormData();
            formData.append('file', file);

            // 根据当前视图选择上传路径
            const uploadUrl = currentView === 'private' ? '/upload/private' : '/upload';

            const xhr = new XMLHttpRequest();

            xhr.upload.addEventListener('progress', (e) => {
                if (e.lengthComputable) {
                    const percent = Math.round((e.loaded / e.total) * 100);
                    progressFill.style.width = percent + '%';
                    progressPercent.textContent = percent + '%';
                }
            });

            xhr.addEventListener('load', () => {
                progressWrap.style.display = 'none';
                const res = JSON.parse(xhr.responseText);
                showToast(res.message, res.success ? 'success' : 'error');
                if (res.success) setTimeout(() => refreshFileList(), 500);
            });

            xhr.addEventListener('error', () => {
                progressWrap.style.display = 'none';
                showToast('上传失败，请重试', 'error');
            });

            xhr.open('POST', uploadUrl);
            xhr.send(formData);
        }

        // 删除文件
        function deleteFile(filename) {
            if (!confirm(`确定删除 "${filename}"？`)) return;

            // 根据当前视图选择删除路径
            const deleteUrl = currentView === 'private'
                ? `/delete/private/${encodeURIComponent(filename)}`
                : `/delete/${encodeURIComponent(filename)}`;

            fetch(deleteUrl, { method: 'POST' })
                .then(r => r.json())
                .then(data => {
                    showToast(data.message, data.success ? 'success' : 'error');
                    if (data.success) setTimeout(() => refreshFileList(), 500);
                })
                .catch(() => showToast('删除失败', 'error'));
        }

        // 打开文件预览
        function openFile(filename, view) {
            // 根据视图选择预览路径
            const openUrl = view === 'private'
                ? `/view/private/${filename}`
                : `/view/${filename}`;
            // 在新标签页中打开文件，浏览器会根据文件类型自动处理
            window.open(openUrl, '_blank');
        }
        
        // 提示消息
        function showToast(message, type) {
            const toast = document.createElement('div');
            toast.className = `toast ${type}`;
            toast.innerHTML = type === 'success' 
                ? `<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>${message}`
                : `<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/></svg>${message}`;
            document.body.appendChild(toast);
            setTimeout(() => toast.remove(), 3000);
        }
        
        // 刷新文件列表
        let isRefreshing = false;

        function refreshFileList() {
            if (isRefreshing) return;

            isRefreshing = true;
            const btn = document.getElementById('btn-refresh');
            const fileList = document.getElementById('file-list');
            const loading = document.getElementById('file-list-loading');

            // 设置加载状态
            btn.classList.add('loading');
            btn.disabled = true;
            fileList.style.display = 'none';
            loading.style.display = 'block';

            // 创建超时控制器
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 10000);

            // 根据当前视图选择API路径
            const apiUrl = currentView === 'private' ? '/api/my-files' : '/api/files';

            fetch(apiUrl, { signal: controller.signal })
                .then(response => {
                    clearTimeout(timeoutId);
                    if (!response.ok) {
                        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                    }
                    return response.json();
                })
                .then(data => {
                    if (data.success) {
                        updateFileListUI(data.files);
                        document.getElementById('file-count').textContent = `(${data.files.length})`;
                        showToast('文件列表已更新', 'success');
                    } else {
                        throw new Error(data.message || '获取文件列表失败');
                    }
                })
                .catch(err => {
                    let errorMsg = '刷新失败，请重试';

                    if (err.name === 'AbortError') {
                        errorMsg = '请求超时，请检查网络连接';
                    } else if (err.message && err.message.includes('403')) {
                        errorMsg = '权限不足，无法访问文件列表';
                    } else if (err.message && err.message.includes('404')) {
                        errorMsg = '服务不可用，请稍后重试';
                    } else if (err.message && (err.message.includes('NetworkError') || err.message.includes('fetch'))) {
                        errorMsg = '网络连接失败，请检查网络';
                    } else if (err.message) {
                        errorMsg = err.message;
                    }

                    showToast(errorMsg, 'error');
                    console.error('刷新文件列表失败:', err);
                })
                .finally(() => {
                    // 恢复UI状态
                    btn.classList.remove('loading');
                    btn.disabled = false;
                    fileList.style.display = 'block';
                    loading.style.display = 'none';
                    isRefreshing = false;
                });
        }
        
        // 更新文件列表UI
        function updateFileListUI(files) {
            const fileList = document.getElementById('file-list');
            
            if (files.length === 0) {
                fileList.innerHTML = `
                    <div class="empty-state">
                        <div class="empty-icon">
                            <svg viewBox="0 0 24 24"><path d="M20 6h-8l-2-2H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2zm0 12H4V8h16v10z"/></svg>
                        </div>
                        <div class="empty-text">暂无文件，请上传第一个文件</div>
                    </div>
                `;
                return;
            }
            
            fileList.innerHTML = files.map(file => {
                const uploaderHtml = file.uploader_name
                    ? `<span class="file-uploader">
                        <svg viewBox="0 0 24 24"><path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/></svg>
                        ${escapeHtml(file.uploader_name)}
                       </span>`
                    : '';

                return `
                <div class="file-item">
                    <div class="file-thumb">
                        <svg viewBox="0 0 24 24"><path d="M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z"/></svg>
                    </div>
                    <div class="file-info">
                        <div class="file-name">${escapeHtml(file.name)}</div>
                        <div class="file-meta">
                            <span>${file.formatted_size} · ${file.modified}</span>
                            ${uploaderHtml}
                        </div>
                    </div>
                    <div class="file-actions">
                        <a href="/download/${encodeURIComponent(file.name)}" class="btn btn-primary">
                            <svg viewBox="0 0 24 24"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/></svg>
                            下载
                        </a>
                        <button class="btn btn-danger" onclick="deleteFile('${encodeURIComponent(file.name)}')">
                            <svg viewBox="0 0 24 24"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg>
                            删除
                        </button>
                    </div>
                </div>
            `}).join('');
        }
        
        // HTML转义防止XSS
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
    </script>
</body>
</html>
'''

if __name__ == '__main__':
    import sys
    if sys.platform == 'win32':
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

    local_ip = get_local_ip()

    print("=" * 60)
    print("🚀 局域网文件分享中心 v2.0 已启动！")
    print("=" * 60)
    print(f"📍 本机访问: http://127.0.0.1:{PORT}")
    print(f"🌐 局域网访问: http://{local_ip}:{PORT}")
    print("=" * 60)
    print(f"📁 公共文件目录: {os.path.abspath(file_manager.public_folder)}")
    print(f"📁 个人文件目录: {os.path.abspath(file_manager.user_base_folder)}")
    print(f"👥 用户数据目录: {os.path.abspath(user_manager.user_data_dir)}")
    print(f"📋 日志文件: file_share.log")
    print("=" * 60)
    print(f"📊 最大文件大小: {MAX_FILE_SIZE // 1024 // 1024} MB")
    print(f"🔐 支持用户识别: 是（浏览器指纹 + 8字中文用户名）")
    print("=" * 60)
    print("按 Ctrl+C 停止服务")
    print("=" * 60)

    logger.info(f"服务器启动 - 监听地址: {HOST}:{PORT}")
    logger.info(f"用户功能已启用 - 个人文件和公共文件分离")

    # 运行服务器，允许局域网访问
    app.run(host=HOST, port=PORT, threaded=True)
