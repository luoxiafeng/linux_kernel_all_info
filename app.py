from flask import Flask, render_template, request, redirect, url_for
import os

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads/'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

class Node:
    def __init__(self, name, path, parent=None):
        self.name = name          # 节点名字
        self.path = path          # 节点路径
        self.parent = parent      # 父节点
        self.children = []        # 子节点列表
        self.content = []         # 当前节点的内容

    def add_child(self, child_node):
        self.children.append(child_node)  # 添加子节点

# 定义全局变量
global_path = "/"
parent_node = None

def parse_dts_file(dts_file):
    global global_path, parent_node
    root = Node(name="root", path="/")  # 创建根节点
    parent_node = root  # 初始时，父节点为根节点
    current_node = None

    with open(dts_file, 'r') as file:
        for line in file:
            stripped_line = line.strip()

            # 跳过注释行
            if stripped_line.startswith('/'):
                continue

            # 如果遇到节点开始
            if '{' in stripped_line:
                node_name = stripped_line.split('{')[0].strip()  # 获取节点名
                new_node = Node(name=node_name, path=global_path + node_name + '/', parent=parent_node)  # 创建新节点
                parent_node.add_child(new_node)  # 将新节点添加为父节点的子节点
                current_node = new_node  # 设置当前节点为新节点
                global_path = new_node.path  # 更新global_path
                parent_node = new_node  # 更新当前父节点为新节点

            # 记录节点的内容
            elif '{' not in stripped_line and '}' not in stripped_line:
                if current_node:
                    current_node.content.append(stripped_line)  # 将内容存储到当前节点

            # 如果遇到节点结束
            elif '}' in stripped_line:
                # 结束当前节点，恢复到父节点
                parent_node = parent_node.parent  # 退回到父节点
                global_path = parent_node.path if parent_node else "/"  # 更新global_path
                current_node = parent_node  # 更新当前节点

    return root

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
        root = parse_dts_file(dts_file)
    else:
        root = None

    return render_template('hierarchy.html', root=root)

@app.route('/node_paths')
def node_paths():
    dts_file = 'D:/myproj/deviceTreeTool/uploads/test.dts'  # 使用实际的文件路径
    if os.path.exists(dts_file):
        root = parse_dts_file(dts_file)
    else:
        root = None

    return render_template('node_paths.html', root=root)

if __name__ == '__main__':
    app.run(debug=True)
