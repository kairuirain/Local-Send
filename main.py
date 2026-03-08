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
from datetime import datetime
from flask import Flask, render_template_string, request, send_file, jsonify, redirect, url_for
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge

# 配置
UPLOAD_FOLDER = 'files'
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'zip', 'rar', '7z', 'mp3', 'mp4', 'avi', 'mov', 'py', 'js', 'html', 'css', 'json', 'xml', 'md'}
MAX_FILE_SIZE = 1024 * 1024 * 1024 * 5 # 5GB

# 创建Flask应用
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE
app.secret_key = 'localshare-secret-key-2026'

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

# 确保上传目录存在
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

def get_file_size(file_path):
    """获取文件大小并格式化显示"""
    size = os.path.getsize(file_path)
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} TB"

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

def get_files_list():
    """获取文件列表"""
    files = []
    try:
        for filename in os.listdir(UPLOAD_FOLDER):
            file_path = os.path.join(UPLOAD_FOLDER, filename)
            if os.path.isfile(file_path):
                files.append({
                    'name': filename,
                    'size': get_file_size(file_path),
                    'modified': datetime.fromtimestamp(os.path.getmtime(file_path)).strftime('%Y-%m-%d %H:%M:%S')
                })
        files.sort(key=lambda x: x['modified'], reverse=True)
    except Exception as e:
        logger.error(f"读取文件列表失败: {e}")
        raise
    return files

@app.route('/')
def index():
    """主页 - 显示文件列表"""
    try:
        files = get_files_list()
    except Exception:
        files = []
    return render_template_string(HTML_TEMPLATE, files=files, local_ip=get_local_ip())

@app.route('/api/files')
def api_files():
    """API: 获取文件列表（用于刷新）"""
    try:
        files = get_files_list()
        return jsonify({'success': True, 'files': files})
    except PermissionError as e:
        logger.error(f"权限不足，无法读取文件列表: {e}")
        return jsonify({'success': False, 'message': '权限不足，无法访问文件目录'}), 403
    except FileNotFoundError as e:
        logger.error(f"文件目录不存在: {e}")
        return jsonify({'success': False, 'message': '文件存储目录不存在'}), 500
    except Exception as e:
        logger.error(f"获取文件列表失败: {e}")
        return jsonify({'success': False, 'message': '获取文件列表失败，请稍后重试'}), 500

@app.route('/upload', methods=['POST'])
def upload_file():
    """处理文件上传"""
    if 'file' not in request.files:
        logger.warning("上传请求中没有文件")
        return jsonify({'success': False, 'message': '没有选择文件'}), 400
    
    file = request.files['file']
    if file.filename == '':
        logger.warning("上传的文件名为空")
        return jsonify({'success': False, 'message': '没有选择文件'}), 400
    
    if file and allowed_file(file.filename):
        filename = safe_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        # 如果文件已存在，添加数字后缀
        counter = 1
        original_filename = filename
        while os.path.exists(file_path):
            name, ext = os.path.splitext(original_filename)
            filename = f"{name}_{counter}{ext}"
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            counter += 1
        
        try:
            file.save(file_path)
            logger.info(f"文件上传成功: {filename}")
            return jsonify({
                'success': True, 
                'message': f'文件 "{filename}" 上传成功！',
                'filename': filename
            })
        except Exception as e:
            logger.error(f"文件上传失败: {e}")
            return jsonify({'success': False, 'message': f'上传失败: {str(e)}'}), 500
    else:
        logger.warning(f"不允许的文件类型: {file.filename}")
        return jsonify({'success': False, 'message': '不允许的文件类型'}), 400

@app.route('/download/<path:filename>')
def download_file(filename):
    """处理文件下载"""
    try:
        # URL解码文件名
        filename = urllib.parse.unquote(filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        # 安全检查：确保文件路径在UPLOAD_FOLDER内
        real_file_path = os.path.realpath(file_path)
        real_upload_folder = os.path.realpath(app.config['UPLOAD_FOLDER'])
        if not real_file_path.startswith(real_upload_folder):
            logger.warning(f"非法文件路径: {filename}")
            return jsonify({'success': False, 'message': '非法文件路径'}), 403
        
        if not os.path.exists(file_path):
            logger.warning(f"下载的文件不存在: {filename}")
            return jsonify({'success': False, 'message': '文件不存在'}), 404
        
        logger.info(f"文件下载: {filename}")
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
    """删除文件"""
    try:
        # URL解码文件名
        filename = urllib.parse.unquote(filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        # 安全检查：确保文件路径在UPLOAD_FOLDER内
        real_file_path = os.path.realpath(file_path)
        real_upload_folder = os.path.realpath(app.config['UPLOAD_FOLDER'])
        if not real_file_path.startswith(real_upload_folder):
            logger.warning(f"非法文件路径: {filename}")
            return jsonify({'success': False, 'message': '非法文件路径'}), 403
        
        if not os.path.exists(file_path):
            return jsonify({'success': False, 'message': '文件不存在'}), 404
        
        os.remove(file_path)
        logger.info(f"文件删除成功: {filename}")
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
    logger.error(f"服务器错误: {e}")
    return jsonify({'success': False, 'message': '服务器内部错误'}), 500

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
                <span>http://{{ local_ip }}:8080</span>
            </div>
        </div>
        
        <!-- 上传区域 -->
        <div class="card">
            <div class="upload-zone" id="upload-zone">
                <div class="upload-icon">
                    <svg viewBox="0 0 24 24"><path d="M9 16h6v-6h4l-7-7-7 7h4v6zm-4 2h14v2H5v-2z"/></svg>
                </div>
                <div class="upload-title">点击或拖拽文件到此处上传</div>
                <div class="upload-hint">支持多种文件格式，单个文件最大 500MB</div>
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
                <div class="file-item">
                    <div class="file-thumb">
                        <svg viewBox="0 0 24 24"><path d="M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z"/></svg>
                    </div>
                    <div class="file-info">
                        <div class="file-name">{{ file.name }}</div>
                        <div class="file-meta">{{ file.size }} · {{ file.modified }}</div>
                    </div>
                    <div class="file-actions">
                        <a href="/download/{{ file.name | urlencode }}" class="btn btn-primary">
                            <svg viewBox="0 0 24 24"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/></svg>
                            下载
                        </a>
                        <button class="btn btn-danger" onclick="deleteFile('{{ file.name | urlencode }}')">
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
        
        // 点击上传
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
        
        // 上传文件
        function uploadFile(file) {
            progressWrap.style.display = 'block';
            progressFill.style.width = '0%';
            progressFile.textContent = file.name;
            progressPercent.textContent = '0%';
            
            const formData = new FormData();
            formData.append('file', file);
            
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
                if (res.success) setTimeout(() => location.reload(), 800);
            });
            
            xhr.addEventListener('error', () => {
                progressWrap.style.display = 'none';
                showToast('上传失败，请重试', 'error');
            });
            
            xhr.open('POST', '/upload');
            xhr.send(formData);
        }
        
        // 删除文件
        function deleteFile(filename) {
            if (!confirm(`确定删除 "${filename}"？`)) return;
            
            fetch(`/delete/${encodeURIComponent(filename)}`, { method: 'POST' })
                .then(r => r.json())
                .then(data => {
                    showToast(data.message, data.success ? 'success' : 'error');
                    if (data.success) setTimeout(() => location.reload(), 800);
                })
                .catch(() => showToast('删除失败', 'error'));
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
            const timeoutId = setTimeout(() => controller.abort(), 10000); // 10秒超时
            
            fetch('/api/files', { signal: controller.signal })
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
                .catch(error => {
                    let errorMsg = '刷新失败，请重试';
                    
                    if (error.name === 'AbortError') {
                        errorMsg = '请求超时，请检查网络连接';
                    } else if (error.message.includes('403')) {
                        errorMsg = '权限不足，无法访问文件列表';
                    } else if (error.message.includes('404')) {
                        errorMsg = '服务不可用，请稍后重试';
                    } else if (error.message.includes('NetworkError') || error.message.includes('fetch')) {
                        errorMsg = '网络连接失败，请检查网络';
                    } else if (error.message) {
                        errorMsg = error.message;
                    }
                    
                    showToast(errorMsg, 'error');
                    logger.error('刷新文件列表失败:', error);
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
            
            fileList.innerHTML = files.map(file => `
                <div class="file-item">
                    <div class="file-thumb">
                        <svg viewBox="0 0 24 24"><path d="M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z"/></svg>
                    </div>
                    <div class="file-info">
                        <div class="file-name">${escapeHtml(file.name)}</div>
                        <div class="file-meta">${file.size} · ${file.modified}</div>
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
            `).join('');
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
    local_ip = get_local_ip()
    print("=" * 60)
    print("🚀 局域网文件分享中心已启动！")
    print("=" * 60)
    print(f"📍 本机访问: http://127.0.0.1:8080")
    print(f"🌐 局域网访问: http://{local_ip}:8080")
    print("=" * 60)
    print(f"📁 文件存储目录: {os.path.abspath(UPLOAD_FOLDER)}")
    print(f"📋 日志文件: file_share.log")
    print("=" * 60)
    print("按 Ctrl+C 停止服务")
    print("=" * 60)
    
    logger.info(f"服务器启动 - 监听地址: 0.0.0.0:8080")
    
    # 运行服务器，允许局域网访问
    app.run(host='0.0.0.0', port=8080, debug=False, threaded=True)
