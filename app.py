from flask import Flask, render_template, request, redirect, url_for
import os

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads/'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def parse_dts_file(dts_file):
    with open(dts_file, 'r') as file:
        lines = file.readlines()

    depth = 0
    node_stack = []  # 用于存储节点的栈
    root_nodes = []  # 用于存储根节点
    children = {}  # 存储根节点的子节点

    for line in lines:
        stripped_line = line.strip()

        # 跳过注释行
        if stripped_line.startswith('/'):
            continue

        # 如果遇到节点开始，增加深度
        if '{' in stripped_line:
            node_name = stripped_line.split('{')[0].strip()  # 获取节点名
            if depth == 0:  # 如果是根节点
                root_nodes.append(node_name)
                children[node_name] = []  # 初始化子节点列表
            else:
                if depth == 1:  # 深度为 1 表示是根节点的子节点
                    parent_node = node_stack[-1] if node_stack else None
                    if parent_node in children:
                        children[parent_node].append(node_name)  # 添加子节点
            node_stack.append(node_name)  # 入栈
            depth += 1
        # 如果遇到节点结束，减少深度
        elif '}' in stripped_line:
            if depth > 0:  # 确保 depth 大于 0
                depth -= 1
                node_stack.pop()  # 出栈

    return root_nodes, children  # 返回根节点和子节点字典

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return redirect(request.url)
    file = request.files['file']
    if file.filename == '':
        return redirect(request.url)

    # 保存文件
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
    file.save(file_path)
    return redirect(url_for('hierarchy'))

@app.route('/hierarchy')
def hierarchy():
    dts_file = 'D:/myproj/deviceTreeTool/uploads/test.dts'  # 使用实际的文件路径
    if os.path.exists(dts_file):
        root_nodes, children = parse_dts_file(dts_file)
        device_tree = {node: children[node] for node in root_nodes}
    else:
        device_tree = {}

    return render_template('hierarchy.html', device_tree=device_tree)

if __name__ == '__main__':
    app.run(debug=True)
