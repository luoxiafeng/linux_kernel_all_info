# Version: v2.6
from flask import Flask, render_template, request, redirect, url_for, session
from markupsafe import Markup
import os
import shutil

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # 用于session
app.config['UPLOAD_FOLDER'] = 'uploads/'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

class Node:
    def __init__(self, name, path, parent=None):
        self.name = name
        self.path = path
        self.parent = parent
        self.children = []
        self.content = []
        self.attr = None

    def add_child(self, child_node):
        self.children.append(child_node)

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

global_path = "/"
parent_node = None

def find_inherited_cells(node):
    """递归向上查找 addr_cells 和 size_cells"""
    lookup = False
    origin_node = node
    while node:
        addr_cells = getattr(node.attr, 'addr_cells', None)
        size_cells = getattr(node.attr, 'size_cells', None)
        if addr_cells + size_cells != 0:
            if lookup:
                origin_node.attr.addr_cells = addr_cells
                origin_node.attr.size_cells = size_cells
                origin_node.attr.refnodeattr = node.name
            return addr_cells, size_cells
        node = node.parent
        lookup = True
    raise ValueError("addr_cells and size_cells could not be found in the node hierarchy")

def parse_dts_file(dts_file):
    global global_path, parent_node
    root = Node(name="root", path="/")
    root_attr = attr()
    root.attr = root_attr
    root_attr.node = root
    parent_node = root
    current_node = None
    dts_version = None

    with open(dts_file, 'r') as file:
        for line in file:
            stripped_line = line.strip()
            if stripped_line == '\n' or stripped_line == '':
                continue
            if stripped_line.startswith('/dts-v1/'):
                dts_version = stripped_line
                continue
            if stripped_line.startswith('//'):
                continue
            if stripped_line.startswith('/*'):
                while '*/' not in stripped_line:
                    stripped_line = next(file).strip()
                continue
            if stripped_line.startswith('/ {') or ('/' in stripped_line and '{' in stripped_line):
                global_path = '/'
                root.name = 'root'
                continue
            if '{' in stripped_line:
                node_name = stripped_line.split('{')[0].strip()
                new_node = Node(name=node_name, path=global_path + node_name + '/', parent=parent_node)
                node_attr = attr()
                new_node.attr = node_attr
                node_attr.node = new_node
                parent_node.add_child(new_node)
                current_node = new_node
                global_path = new_node.path
                parent_node = new_node

            elif '{' not in stripped_line and '}' not in stripped_line and global_path != '/':
                if current_node:
                    current_node.content.append(stripped_line)
                if '#address-cells' in stripped_line:
                    try:
                        raw_value = stripped_line.split('=')[1].strip().strip('<>;')
                        current_node.attr.addr_cells = int(raw_value, 16) if raw_value.startswith("0x") else int(raw_value)
                    except (IndexError, ValueError):
                        raise ValueError(f"Invalid format for #address-cells in line: {stripped_line}")
                if '#size-cells' in stripped_line:
                    try:
                        raw_value = stripped_line.split('=')[1].strip().strip('<>;')
                        current_node.attr.size_cells = int(raw_value, 16) if raw_value.startswith("0x") else int(raw_value)
                    except (IndexError, ValueError):
                        raise ValueError(f"Invalid format for #size-cells in line: {stripped_line}")
                if 'phandle' in stripped_line:
                    try:
                        raw_value = stripped_line.split('=')[1].strip().strip('<>;')
                        if raw_value.startswith("0x"):
                            current_node.attr.phandle = int(raw_value, 16)
                        else:
                            current_node.attr.phandle = int(raw_value)
                    except (IndexError, ValueError):
                        raise ValueError(f"Invalid format for phandle in line: {stripped_line}")
                if 'compatible' in stripped_line:
                    try:
                        current_node.attr.compatible = stripped_line.split('=')[1].strip().strip('<>;')
                    except IndexError:
                        raise ValueError(f"Invalid format for compatible in line: {stripped_line}")
                if 'reg = ' in stripped_line:
                    try:
                        reg_values = stripped_line.split('=')[1].strip().strip('<>;').split()
                        reg_values = [int(value, 16) if value.startswith("0x") else int(value) for value in reg_values]
                    except (IndexError, ValueError):
                        raise ValueError(f"Invalid format for reg in line: {stripped_line}")
                    try:
                        addr_cells, size_cells = find_inherited_cells(current_node)
                    except ValueError as e:
                        raise ValueError(f"Cannot parse reg due to missing addr_cells and size_cells: {e}")
                    step = addr_cells + size_cells
                    if len(reg_values) % step != 0:
                        raise ValueError(f"Invalid reg length: {len(reg_values)} for addr_cells: {addr_cells}, size_cells: {size_cells}")
                    regaddr_list = []
                    regsize_list = []
                    for i in range(0, len(reg_values), step):
                        group = reg_values[i:i + step]
                        if len(group) != step:
                            raise ValueError(f"Incomplete reg group: {group}")
                        regaddr = 0
                        for j in range(addr_cells):
                            regaddr = (regaddr << 8) | group[j]
                        regsize = 0
                        for j in range(addr_cells, step):
                            regsize = (regsize << 8) | group[j]
                        regaddr_list.append(regaddr)
                        regsize_list.append(regsize)
                    current_node.attr.regaddr = regaddr_list
                    current_node.attr.regsize = regsize_list

            elif '}' in stripped_line:
                parent_node = current_node.parent
                global_path = parent_node.path if parent_node else "/"
                find_inherited_cells(current_node)
                current_node = parent_node
                
            if global_path == '/':
                if not (stripped_line.__contains__('{') or stripped_line.__contains__('}')):
                    root.content.append(stripped_line)
                    if stripped_line.__contains__('compatible'):
                        root.attr.compatible = stripped_line.split('=')[1].strip().strip('<>;')
                    if stripped_line.__contains__('#address-cells'):
                        raw_value = stripped_line.split('=')[1].strip().strip('<>;')
                        root.attr.addr_cells = int(raw_value, 16) if raw_value.startswith("0x") else int(raw_value)
                    if stripped_line.__contains__('#size-cells'):
                        raw_value = stripped_line.split('=')[1].strip().strip('<>;')
                        root.attr.size_cells = int(raw_value, 16) if raw_value.startswith("0x") else int(raw_value)
    return root

def get_device_tree_files():
    files = []
    for f in os.listdir(app.config['UPLOAD_FOLDER']):
        if f.endswith('.dts'):
            files.append(f)
    return files

def validate_device_tree_file(filepath):
    if filepath.endswith('.dts'):
        return 'dts'
    else:
        return None

# 新增：获取当前dts文件的统一函数
def get_current_dts_file():
    # 如果session中有selected_file并且文件存在，则返回
    if 'selected_file' in session:
        sf = session['selected_file']
        if os.path.exists(sf):
            return sf
    # 如果没选中或者文件不存在，则可以返回None或直接报错
    return None

@app.route('/')
def index():
    return render_template('index.html', files=get_device_tree_files())

@app.route('/select_file', methods=['POST'])
def select_file():
    chosen_file = request.form.get('chosen_file')
    if chosen_file:
        full_path = os.path.join(app.config['UPLOAD_FOLDER'], chosen_file)
        filetype = validate_device_tree_file(full_path)
        if not filetype:
            return "文件格式不对", 400
        session['selected_file'] = full_path
    return redirect(url_for('index'))

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return redirect(request.url)
    file = request.files['file']
    if file.filename == '':
        return redirect(request.url)
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
    file.save(file_path)
    filetype = validate_device_tree_file(file_path)
    if not filetype:
        os.remove(file_path)
        return "文件格式不对", 400
    session['selected_file'] = file_path
    return redirect(url_for('hierarchy'))

@app.route('/hierarchy')
def hierarchy():
    dts_file = get_current_dts_file()
    if not dts_file:
        return "尚未选择或上传有效的 dts 文件", 400
    root = parse_dts_file(dts_file)
    return render_template('hierarchy.html', root=root)

@app.route('/node_paths')
def node_paths():
    dts_file = get_current_dts_file()
    if not dts_file:
        return "尚未选择或上传有效的 dts 文件", 400
    root = parse_dts_file(dts_file)
    return render_template('node_paths.html', root=root)

@app.route('/content')
def content():
    dts_file = get_current_dts_file()
    if not dts_file:
        return "尚未选择或上传有效的 dts 文件", 400
    root = parse_dts_file(dts_file)
    return render_template('content.html', root=root)

@app.route('/interrupt_tree')
def interrupt_tree():
    dts_file = get_current_dts_file()
    if not dts_file:
        return "尚未选择或上传有效的 dts 文件", 400
    root = parse_dts_file(dts_file)
    if not root:
        return render_template('interrupt_tree.html', 
                               controller_nodes=[], 
                               generator_nodes=[], 
                               connector_nodes=[], 
                               ctrl_gen_relations=[], 
                               ctrl_conn_relations=[], 
                               conn_gen_relations=[])

    all_nodes = []
    def collect_nodes(node):
        all_nodes.append(node)
        for c in node.children:
            collect_nodes(c)
    collect_nodes(root)

    phandle_map = {}
    for node in all_nodes:
        if node.attr and node.attr.phandle != 0:
            phandle_map[node.attr.phandle] = node

    controller_nodes = []
    generator_nodes = []
    connector_nodes = []

    for node in all_nodes:
        has_interrupt_controller = any('interrupt-controller' in line for line in node.content)
        has_interrupt_parent = any('interrupt-parent' in line for line in node.content)
        has_interrupt_cells = any('interrupt-cell' in line for line in node.content)

        if has_interrupt_controller and not has_interrupt_parent:
            controller_nodes.append(node)
        elif (not has_interrupt_controller) and (not has_interrupt_cells) and has_interrupt_parent:
            generator_nodes.append(node)
        elif has_interrupt_controller and has_interrupt_parent:
            connector_nodes.append(node)

    ctrl_gen_relations = []
    for g_node in generator_nodes:
        ip_line = [l for l in g_node.content if 'interrupt-parent' in l]
        if ip_line:
            val_str = ip_line[0].split('=')[1].strip().strip('<>;')
            val = int(val_str,16) if val_str.startswith('0x') else int(val_str)
            if val in phandle_map:
                ctrl_node = phandle_map[val]
                if ctrl_node in controller_nodes:
                    ctrl_gen_relations.append((ctrl_node, g_node))

    ctrl_conn_relations = []
    for c_node in connector_nodes:
        ip_line = [l for l in c_node.content if 'interrupt-parent' in l]
        if ip_line:
            val_str = ip_line[0].split('=')[1].strip().strip('<>;')
            val = int(val_str,16) if val_str.startswith('0x') else int(val_str)
            if val in phandle_map:
                ctrl_node = phandle_map[val]
                if ctrl_node in controller_nodes:
                    ctrl_conn_relations.append((ctrl_node, c_node))

    conn_gen_relations = []
    for g_node in generator_nodes:
        ip_line = [l for l in g_node.content if 'interrupt-parent' in l]
        if ip_line:
            val_str = ip_line[0].split('=')[1].strip().strip('<>;')
            val = int(val_str,16) if val_str.startswith('0x') else int(val_str)
            if val in phandle_map:
                parent_node = phandle_map[val]
                if parent_node in connector_nodes:
                    conn_gen_relations.append((parent_node, g_node))

    return render_template('interrupt_tree.html', 
                           controller_nodes=controller_nodes, 
                           generator_nodes=generator_nodes, 
                           connector_nodes=connector_nodes, 
                           ctrl_gen_relations=ctrl_gen_relations, 
                           ctrl_conn_relations=ctrl_conn_relations, 
                           conn_gen_relations=conn_gen_relations)

@app.route('/interrupt_tree_graph')
def interrupt_tree_graph():
    dts_file = get_current_dts_file()
    if not dts_file or not os.path.exists(dts_file):
        uml_code = "@startuml\n' No data\n@enduml"
        return render_template('interrupt_tree_graph.html', uml_code=uml_code)

    root = parse_dts_file(dts_file)
    if not root:
        uml_code = "@startuml\n' No data\n@enduml"
        return render_template('interrupt_tree_graph.html', uml_code=uml_code)

    all_nodes = []
    def collect_nodes(node):
        all_nodes.append(node)
        for c in node.children:
            collect_nodes(c)
    collect_nodes(root)

    phandle_map = {}
    for node in all_nodes:
        if node.attr and node.attr.phandle != 0:
            phandle_map[node.attr.phandle] = node

    controller_nodes = []
    generator_nodes = []
    connector_nodes = []

    for node in all_nodes:
        has_interrupt_controller = any('interrupt-controller' in line for line in node.content)
        has_interrupt_parent = any('interrupt-parent' in line for line in node.content)
        has_interrupt_cells = any('interrupt-cell' in line for line in node.content)

        if has_interrupt_controller and not has_interrupt_parent:
            controller_nodes.append(node)
        elif (not has_interrupt_controller) and (not has_interrupt_cells) and has_interrupt_parent:
            generator_nodes.append(node)
        elif has_interrupt_controller and has_interrupt_parent:
            connector_nodes.append(node)

    ctrl_gen_relations = []
    for g_node in generator_nodes:
        ip_line = [l for l in g_node.content if 'interrupt-parent' in l]
        if ip_line:
            val_str = ip_line[0].split('=')[1].strip().strip('<>;')
            val = int(val_str,16) if val_str.startswith('0x') else int(val_str)
            if val in phandle_map:
                ctrl_node = phandle_map[val]
                if ctrl_node in controller_nodes:
                    ctrl_gen_relations.append((ctrl_node, g_node))

    ctrl_conn_relations = []
    for c_node in connector_nodes:
        ip_line = [l for l in c_node.content if 'interrupt-parent' in l]
        if ip_line:
            val_str = ip_line[0].split('=')[1].strip().strip('<>;')
            val = int(val_str,16) if val_str.startswith('0x') else int(val_str)
            if val in phandle_map:
                ctrl_node = phandle_map[val]
                if ctrl_node in controller_nodes:
                    ctrl_conn_relations.append((ctrl_node, c_node))

    conn_gen_relations = []
    for g_node in generator_nodes:
        ip_line = [l for l in g_node.content if 'interrupt-parent' in l]
        if ip_line:
            val_str = ip_line[0].split('=')[1].strip().strip('<>;')
            val = int(val_str,16) if val_str.startswith('0x') else int(val_str)
            if val in phandle_map:
                parent_node = phandle_map[val]
                if parent_node in connector_nodes:
                    conn_gen_relations.append((parent_node, g_node))

    uml_code = "@startuml\n"
    uml_code += "' 中断控制器使用rectangle表示\n"
    for c in controller_nodes:
        uml_code += f"rectangle \"{c.name}\\n(phandle={c.attr.phandle})\" as C{c.attr.phandle}\n"

    uml_code += "' 中断连接器使用菱形表示\n"
    for conn in connector_nodes:
        uml_code += f"database \"{conn.name}\\n(phandle={conn.attr.phandle})\" as K{conn.attr.phandle}\n"

    uml_code += "' 中断生成设备使用圆括号表示\n"
    for g in generator_nodes:
        uml_code += f"(\"{g.name}\") as G_{id(g)}\n"

    for (ctrl, gen) in ctrl_gen_relations:
        uml_code += f"G_{id(gen)} --> C{ctrl.attr.phandle}\n"
    for (ctrl, conn) in ctrl_conn_relations:
        uml_code += f"K{conn.attr.phandle} --> C{ctrl.attr.phandle}\n"
    for (conn, gen) in conn_gen_relations:
        uml_code += f"G_{id(gen)} --> K{conn.attr.phandle}\n"

    uml_code += "@enduml"

    return render_template('interrupt_tree_graph.html', uml_code=uml_code)

if __name__ == '__main__':
    app.run(debug=True)
