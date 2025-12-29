import os
import pandas as pd
import lightgbm as lgb
import glob
from flask import Flask, request, jsonify, send_file
from werkzeug.utils import secure_filename
import shutil
import tempfile
import zipfile
import io

# 获取当前文件的绝对路径
base_dir = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)
# 修正为绝对路径
app.config['UPLOAD_FOLDER'] = os.path.join(base_dir, 'uploads')

# 模型目录：优先使用服务器路径，如果不存在则使用本地路径
server_model_dir = '/www/wwwroot/www.longevityllmpumc.com/models/17_models'
local_model_dir = os.path.join(base_dir, 'models')
if os.path.exists(server_model_dir):
    app.config['MODEL_DIR'] = server_model_dir
else:
    app.config['MODEL_DIR'] = local_model_dir

app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 限制16MB大小
app.config['ALLOWED_EXTENSIONS'] = {'xlsx', 'xls', 'csv'}

# 确保上传目录存在
try:
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    print(f"已创建上传目录: {app.config['UPLOAD_FOLDER']}")
except Exception as e:
    print(f"创建上传目录失败: {str(e)}")

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def predict_with_models(filepath, user_dir):
    """
    使用所有LightGBM模型对上传的文件进行预测
    返回预测结果文件路径和预测结果摘要
    """
    try:
        # 1. 读取上传的文件
        print(f"开始读取文件: {filepath}")
        if filepath.lower().endswith('.csv'):
            new_data = pd.read_csv(filepath)
        else:  # 假设其他格式为Excel
            new_data = pd.read_excel(filepath)
        
        # 记录文件基本信息
        print(f"成功读取文件，形状: {new_data.shape}")
        
        # 2. 获取所有模型文件
        model_files = glob.glob(os.path.join(app.config['MODEL_DIR'], "*.model"))
        print(f"找到 {len(model_files)} 个模型文件")
        
        if not model_files:
            raise Exception("在模型目录中未找到任何模型文件")
        
        # 3. 创建结果DataFrame
        # 检查是否有ID列
        if 'eid' in new_data.columns:
            results = pd.DataFrame({'eid': new_data['eid'].copy()})
        else:
            # 如果没有ID列，创建临时ID
            results = pd.DataFrame({'row_id': range(1, len(new_data)+1)})
            new_data['row_id'] = results['row_id']
        
        # 4. 处理分类变量（如果需要）
        if 'sex' in new_data.columns:
            new_data['sex'] = new_data['sex'].apply(lambda x: 1 if x == 'male' or x == 1 else 0)
        
        # 5. 循环遍历每个模型并进行预测
        for model_file in model_files:
            try:
                # 提取模型名称（不含扩展名）
                model_name = os.path.basename(model_file).replace(".model", "")
                print(f"处理模型: {model_name}")
                
                # 加载模型
                bst = lgb.Booster(model_file=model_file)
                
                # 获取模型特征顺序
                model_features = bst.feature_name()
                
                # 检查缺失特征
                missing_features = set(model_features) - set(new_data.columns)
                if missing_features:
                    print(f"警告: 缺失 {len(missing_features)} 个特征，自动填充0值")
                    # 为缺失特征添加0值列
                    for feature in missing_features:
                        new_data[feature] = 0
                
                # 按模型要求的特征顺序排列数据
                X_predict = new_data[model_features]
                
                # 执行预测
                predictions = bst.predict(X_predict)
                print(f"预测完成，结果数: {len(predictions)}")
                
                # 将预测结果添加到结果DataFrame
                results[model_name] = predictions
                
            except Exception as e:
                print(f"处理模型 {model_name} 时出错: {str(e)}")
                results[model_name] = None  # 添加空列
        
        # 6. 保存结果
        # 创建结果文件名
        original_filename = os.path.basename(filepath)
        result_filename = f"predictions_{original_filename}"
        result_filepath = os.path.join(user_dir, result_filename)
        
        # 保存为CSV
        results.to_csv(result_filepath, index=False)
        print(f"预测结果已保存到: {result_filepath}")
        
        # 计算每个模型的平均预测值（摘要）
        summary = {}
        for column in results.columns:
            if column not in ['eid', 'row_id'] and pd.api.types.is_numeric_dtype(results[column]):
                summary[column] = results[column].mean()
        
        return result_filepath, summary
        
    except Exception as e:
        print(f"预测过程中发生错误: {str(e)}")
        raise

@app.route('/api/login', methods=['POST'])
def login_api():
    # 检查文件是否上传
    if 'file' not in request.files:
        return jsonify(success=False, error="未上传文件"), 400
    
    file = request.files['file']
    username = request.form.get('username', '匿名用户')
    
    # 检查用户名是否有效
    if not username or len(username) < 2:
        return jsonify(success=False, error="用户名至少需要2个字符"), 400
    
    # 检查文件名是否为空
    if file.filename == '':
        return jsonify(success=False, error="未选择文件"), 400
    
    if file and allowed_file(file.filename):
        # 安全保存文件名
        filename = secure_filename(file.filename)
        
        # 创建用户目录（使用绝对路径）
        user_dir = os.path.join(app.config['UPLOAD_FOLDER'], username)
        try:
            os.makedirs(user_dir, exist_ok=True)
            print(f"已创建用户目录: {user_dir}")
        except Exception as e:
            return jsonify(
                success=False,
                error=f"创建用户目录失败: {str(e)}"
            ), 500
        
        # 保存文件路径（绝对路径）
        filepath = os.path.join(user_dir, filename)
        try:
            file.save(filepath)
            print(f"文件已保存到: {filepath}")
        except Exception as e:
            return jsonify(
                success=False,
                error=f"文件保存失败: {str(e)}"
            ), 500
        
        # 进行模型预测
        try:
            result_filepath, prediction_summary = predict_with_models(filepath, user_dir)
            result_filename = os.path.basename(result_filepath)
            
            # 返回成功响应
            return jsonify(
                success=True, 
                message="文件上传成功并已完成预测",
                filename=filename,
                filepath=filepath,
                prediction_file=result_filename,
                prediction_summary=prediction_summary
            )
        except Exception as e:
            return jsonify(
                success=False,
                error=f"预测过程中发生错误: {str(e)}"
            ), 500
        
    else:
        return jsonify(success=False, error="仅支持Excel(.xlsx/.xls)和CSV文件"), 400

@app.route('/api/download/<username>/<filename>', methods=['GET'])
def download_file(username, filename):
    """下载预测结果文件"""
    # 构建文件路径
    user_dir = os.path.join(app.config['UPLOAD_FOLDER'], username)
    filepath = os.path.join(user_dir, filename)
    
    # 检查文件是否存在
    if not os.path.exists(filepath):
        return jsonify(success=False, error="文件不存在"), 404
    
    # 返回文件下载
    return send_file(
        filepath,
        as_attachment=True,
        download_name=filename
    )

@app.route('/api/download-all/<username>', methods=['GET'])
def download_all_files(username):
    """下载用户所有文件（ZIP格式）"""
    user_dir = os.path.join(app.config['UPLOAD_FOLDER'], username)
    
    # 检查用户目录是否存在
    if not os.path.exists(user_dir):
        return jsonify(success=False, error="用户目录不存在"), 404
    
    # 创建临时ZIP文件
    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(user_dir):
            for file in files:
                file_path = os.path.join(root, file)
                # 在ZIP文件中使用相对路径
                arcname = os.path.relpath(file_path, start=user_dir)
                zf.write(file_path, arcname=os.path.join(username, arcname))
    
    memory_file.seek(0)
    
    # 返回ZIP文件下载
    return send_file(
        memory_file,
        as_attachment=True,
        download_name=f"{username}_files.zip",
        mimetype='application/zip'
    )

if __name__ == '__main__':
    # 检查模型目录是否存在
    if not os.path.exists(app.config['MODEL_DIR']):
        print(f"警告: 模型目录不存在 {app.config['MODEL_DIR']}")
    
    app.run(host='0.0.0.0', port=5000, debug=True)
