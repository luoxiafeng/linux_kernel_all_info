from flask import Flask, render_template, request, redirect, url_for
from markupsafe import Markup
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
        self.attr = None

    def add_child(self, child_node):
        self.children.append(child_node)  # 添加子节点
class attr:
    def __init__(self):
        self.addr_cells = 0
        self.size_cells = 0
        self.refnodeattr = ""
        self.phandle = 0
        self.compatible = ""
        self.regaddr = []
        self.regsize = []
        self.node = None

# 定义全局变量
global_path = "/"
parent_node = None

def find_inherited_cells(node):
    """递归向上查找 addr_cells 和 size_cells"""
    lookup = False
    origin_node = node
    while node:
        addr_cells = getattr(node.attr, 'addr_cells', None)
        size_cells = getattr(node.attr, 'size_cells', None)
        # 如果不等于0，说明找到了
        if addr_cells + size_cells != 0:
            if lookup:
                origin_node.attr.addr_cells = addr_cells
                origin_node.attr.size_cells = size_cells
                origin_node.attr.refnodeattr = node.name
            return addr_cells, size_cells
        node = node.parent  # 向上查找
        lookup = True
    raise ValueError("addr_cells and size_cells could not be found in the node hierarchy")

def parse_dts_file(dts_file):
    global global_path, parent_node
    root = Node(name="root", path="/")  # 创建根节点
    root_attr = attr() # 创建根节点属性
    root.attr = root_attr # 将属性添加到根节点
    root_attr.node = root # 将节点添加到属性
    parent_node = root  # 初始时，父节点为根节点
    current_node = None
    dts_version = None

    with open(dts_file, 'r') as file:
        for line in file:
            stripped_line = line.strip()
            # 跳过"\n"
            if stripped_line == '\n' or stripped_line == '':
                continue
            # 跳过版本信息
            if stripped_line.startswith('/dts-v1/'):
                dts_version = stripped_line
                continue
            # 跳过注释行
            if stripped_line.startswith('//'):
                continue
            # 如果是/*开头的，跳过注释块
            if stripped_line.startswith('/*'):
                while '*/' not in stripped_line:
                    stripped_line = next(file).strip()
                continue
            # 找到根节点
            if stripped_line.startswith('/ {') or (stripped_line.__contains__('/') and stripped_line.__contains__('{')):
                global_path = '/'
                root.name = 'root'
                continue
          
            # 如果遇到节点开始
            if '{' in stripped_line:
                node_name = stripped_line.split('{')[0].strip()  # 获取节点名
                new_node = Node(name=node_name, path=global_path + node_name + '/', parent=parent_node)  # 创建新节点
                node_attr = attr() # 创建新节点属性
                new_node.attr = node_attr # 将属性添加到新节点
                node_attr.node = new_node # 将节点添加到属性
                parent_node.add_child(new_node)  # 将新节点添加为父节点的子节点
                current_node = new_node  # 设置当前节点为新节点
                global_path = new_node.path  # 更新global_path
                parent_node = new_node  # 更新当前父节点为新节点

            # 记录节点的内容
            elif '{' not in stripped_line and '}' not in stripped_line and global_path != '/':
                if current_node:
                    current_node.content.append(stripped_line)  # 将内容存储到当前节点

                # 检查并解析 #address-cells
                if '#address-cells' in stripped_line:
                    try:
                        raw_value = stripped_line.split('=')[1].strip()
                        raw_value = raw_value.strip('<>;')  # 去掉尖括号和分号
                        current_node.attr.addr_cells = int(raw_value, 16) if raw_value.startswith("0x") else int(raw_value)
                    except (IndexError, ValueError):
                        raise ValueError(f"Invalid format for #address-cells in line: {stripped_line}")

                # 检查并解析 #size-cells
                if '#size-cells' in stripped_line:
                    try:
                        raw_value = stripped_line.split('=')[1].strip()
                        raw_value = raw_value.strip('<>;')  # 去掉尖括号和分号
                        current_node.attr.size_cells = int(raw_value, 16) if raw_value.startswith("0x") else int(raw_value)
                    except (IndexError, ValueError):
                        raise ValueError(f"Invalid format for #size-cells in line: {stripped_line}")

                # 检查并解析 phandle
                if 'phandle' in stripped_line:
                    try:
                        raw_value = stripped_line.split('=')[1].strip().strip('<>;')  # 去掉尖括号和分号
                        if raw_value.startswith("0x"):
                            current_node.attr.phandle = int(raw_value, 16)  # 十六进制解析
                        else:
                            current_node.attr.phandle = int(raw_value)  # 十进制解析
                    except (IndexError, ValueError):
                        raise ValueError(f"Invalid format for phandle in line: {stripped_line}")

                # 检查并解析 compatible
                if 'compatible' in stripped_line:
                    try:
                        current_node.attr.compatible = stripped_line.split('=')[1].strip().strip('<>;')
                    except IndexError:
                        raise ValueError(f"Invalid format for compatible in line: {stripped_line}")

                # 检查并解析 reg
                if 'reg = ' in stripped_line:  # 解析 reg 属性
                    try:
                        # 提取 reg 值并转为整数列表
                        reg_values = stripped_line.split('=')[1].strip().strip('<>;').split()
                        reg_values = [int(value, 16) if value.startswith("0x") else int(value) for value in reg_values]
                    except (IndexError, ValueError):
                        raise ValueError(f"Invalid format for reg in line: {stripped_line}")

                    # 查找 address_cells 和 size_cells
                    try:
                        addr_cells, size_cells = find_inherited_cells(current_node)
                    except ValueError as e:
                        raise ValueError(f"Cannot parse reg due to missing addr_cells and size_cells: {e}")

                    # 验证总长度是否可以整除 addr_cells + size_cells
                    step = addr_cells + size_cells
                    if len(reg_values) % step != 0:
                        raise ValueError(f"Invalid reg length: {len(reg_values)} for addr_cells: {addr_cells}, size_cells: {size_cells}")

                    # 逐对解析地址和大小
                    regaddr_list = []
                    regsize_list = []
                    for i in range(0, len(reg_values), step):
                        group = reg_values[i:i + step]
                        if len(group) != step:
                            raise ValueError(f"Incomplete reg group: {group}")

                        # 地址解析：从高字节到低字节拼接
                        regaddr = 0
                        for j in range(addr_cells):
                            regaddr = (regaddr << 8) | group[j]

                        # 大小解析：从高字节到低字节拼接
                        regsize = 0
                        for j in range(addr_cells, step):
                            regsize = (regsize << 8) | group[j]

                        regaddr_list.append(regaddr)
                        regsize_list.append(regsize)

                    # 保存解析结果
                    current_node.attr.regaddr = regaddr_list
                    current_node.attr.regsize = regsize_list

            # 如果遇到节点结束
            elif '}' in stripped_line:
                # 结束当前节点，恢复到父节点
                parent_node = current_node.parent  # 退回到父节点
                global_path = parent_node.path if parent_node else "/"  # 更新global_path
                current_node = parent_node  # 更新当前节点
                
            # 如果是根节点，将根节点和第一个子节点之间的内容保存到根节点内容中
            if global_path == '/':
                if not (stripped_line.__contains__('{') or stripped_line.__contains__('}')):
                    root.content.append(stripped_line)
                    if stripped_line.__contains__('compatible'):
                        root_attr.compatible = stripped_line.split('=')[1].strip().strip('<>;')
                    if stripped_line.__contains__('#address-cells'):
                        raw_value = stripped_line.split('=')[1].strip().strip('<>;')
                        root_attr.addr_cells = int(raw_value, 16) if raw_value.startswith("0x") else int(raw_value)
                    if stripped_line.__contains__('#size-cells'):
                        raw_value = stripped_line.split('=')[1].strip().strip('<>;')
                        root_attr.size_cells = int(raw_value, 16) if raw_value.startswith("0x") else int(raw_value)
 
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

@app.route('/content')
def content():
    dts_file = 'D:/myproj/deviceTreeTool/uploads/test.dts'  # 使用实际的文件路径
    if os.path.exists(dts_file):
        root = parse_dts_file(dts_file)
    else:
        root = None

    return render_template('content.html', root=root)


if __name__ == '__main__':
    app.run(debug=True)
