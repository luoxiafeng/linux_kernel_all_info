# Version: v2.6 (enhanced reg parsing)
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
power_domain_controllers = []
power_domain_relations = []
clock_controllers = []
clock_relations = []
memory_node = None
reserved_memory_nodes = []


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
    global power_domain_controllers, power_domain_relations, clock_controllers, clock_relations, memory_node, reserved_memory_nodes
    power_domain_controllers.clear()
    power_domain_relations.clear()
    clock_controllers.clear()
    clock_relations.clear()
    memory_node = None
    reserved_memory_nodes.clear()
    
    root = Node(name="root", path="/")
    root_attr = attr()
    root.attr = root_attr
    root_attr.node = root
    parent_node = root
    current_node = None
    dts_version = None

    def handle_comment_line(line_iter, line):
        # 处理/* ... */注释，多行可能性
        result = ""
        pos = 0
        while True:
            start = line.find('/*', pos)
            if start == -1:
                # 没有/*，整行保留
                result += line[pos:]
                break
            else:
                # 有/*，保留之前的内容
                result += line[pos:start]
                end = line.find('*/', start+2)
                if end == -1:
                    # 当前行没有结束注释，丢弃后续
                    while True:
                        try:
                            next_line = next(line_iter)
                        except StopIteration:
                            # 文件结束仍未找到*/
                            break
                        cpos = next_line.find('*/')
                        if cpos == -1:
                            # 整行都是注释
                            continue
                        else:
                            # 找到*/，该行从*/后面开始
                            after = next_line[cpos+2:].strip()
                            line = after  # 更新line，继续处理可能后面的/*注释
                            pos = 0
                            break
                else:
                    # 同行结束注释，保留*/后的内容
                    pos = end+2
                    # 不break，可能有多个注释段
        return result.strip()

    with open(dts_file, 'r') as file:
        line_iter = iter(file)
        while True:
            try:
                line = next(line_iter)
            except StopIteration:
                break
            stripped_line = line.strip()
            if stripped_line == '' or stripped_line == '\n':
                continue

            # 先处理/* ... */多行注释
            if '/*' in stripped_line:
                stripped_line = handle_comment_line(line_iter, stripped_line)
                if stripped_line == '':
                    continue  # 注释可能清空这行

            # 处理 // 注释：如果//在行首，则跳过该行
            if stripped_line.startswith('//'):
                continue
            # 如果//在中间，只保留//前面的部分
            slash_pos = stripped_line.find('//')
            if slash_pos != -1:
                stripped_line = stripped_line[:slash_pos].strip()
                if stripped_line == '':
                    continue

            if stripped_line.startswith('/dts-v1/'):
                dts_version = stripped_line
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
                        raw_value = stripped_line.split('=')[1].strip('<>; ')
                        current_node.attr.addr_cells = int(raw_value, 0)
                    except:
                        raise ValueError(f"Invalid format for #address-cells in line: {stripped_line}")

                if '#size-cells' in stripped_line:
                    try:
                        raw_value = stripped_line.split('=')[1].strip('<>; ')
                        current_node.attr.size_cells = int(raw_value, 0)
                    except:
                        raise ValueError(f"Invalid format for #size-cells in line: {stripped_line}")

                if 'phandle' in stripped_line:
                    try:
                        raw_value = stripped_line.split('=')[1].strip('<>; ')
                        if raw_value.startswith("0x"):
                            current_node.attr.phandle = int(raw_value, 16)
                        else:
                            current_node.attr.phandle = int(raw_value)
                    except:
                        raise ValueError(f"Invalid format for phandle in line: {stripped_line}")

                if 'compatible' in stripped_line:
                    try:
                        current_node.attr.compatible = stripped_line.split('=')[1].strip('<>; ')
                    except:
                        raise ValueError(f"Invalid format for compatible in line: {stripped_line}")

                if 'reg = ' in stripped_line:
                    reg_line = stripped_line
                    while ';' not in reg_line:
                        next_line = next(line_iter).strip()
                        if current_node:
                            current_node.content.append(next_line)
                        reg_line += ' ' + next_line

                    reg_line_processed = reg_line.split('=')[1].strip().strip(';')
                    groups = reg_line_processed.split('>')
                    all_values = []
                    for g in groups:
                        g = g.replace('<','').replace(',','').strip()
                        if g:
                            vals = g.split()
                            for v in vals:
                                if v.startswith("0x"):
                                    all_values.append(int(v,16))
                                else:
                                    all_values.append(int(v))
                    try:
                        addr_cells, size_cells = find_inherited_cells(current_node)
                    except ValueError as e:
                        raise ValueError(f"Cannot parse reg due to missing addr_cells and size_cells: {e}")

                    step = addr_cells + size_cells
                    if len(all_values) % step != 0:
                        print(stripped_line)
                        raise ValueError(f"Invalid reg length: {len(all_values)} for addr_cells: {addr_cells}, size_cells: {size_cells}")

                    regaddr_list = []
                    regsize_list = []
                    for i in range(0, len(all_values), step):
                        group = all_values[i:i+step]
                        if len(group) != step:
                            raise ValueError(f"Incomplete reg group: {group}")
                        regaddr = 0
                        for j in range(addr_cells):
                            regaddr = (regaddr << 32) | group[j]
                        regsize = 0
                        for j in range(addr_cells, step):
                            regsize = (regsize << 32) | group[j]
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
                if not ('{' in stripped_line or '}' in stripped_line):
                    root.content.append(stripped_line)
                    if 'compatible' in stripped_line:
                        root.attr.compatible = stripped_line.split('=')[1].strip('<>; ')
                    if '#address-cells' in stripped_line:
                        raw_value = stripped_line.split('=')[1].strip('<>; ')
                        root.attr.addr_cells = int(raw_value, 0)
                    if '#size-cells' in stripped_line:
                        raw_value = stripped_line.split('=')[1].strip('<>; ')
                        root.attr.size_cells = int(raw_value, 0)

     # 解析节点，获取全部节点列表
    all_nodes = []
    def collect_nodes(node):
        all_nodes.append(node)
        for c in node.children:
            collect_nodes(c)
    collect_nodes(root)

    # 电源域解析
    pd_phandle_map = {}
    for node in all_nodes:
        has_pdcells = any('#power-domain-cells' in l for l in node.content)
        if has_pdcells:
            power_domain_controllers.append(node)
            if node.attr.phandle != 0:
                pd_phandle_map[node.attr.phandle] = node

    for node in all_nodes:
        lines_with_pd = [l for l in node.content if 'power-domains' in l and '=' in l]
        for line_pd in lines_with_pd:
            pd_str = line_pd.split('=')[1].strip().strip('<>;')
            pd_vals = pd_str.split()
            if pd_vals:
                val = pd_vals[0]
                if val.startswith("0x"):
                    pval = int(val,16)
                else:
                    pval = int(val)
                if pval in pd_phandle_map:
                    power_domain_relations.append((pd_phandle_map[pval], node))

    # 时钟树解析
    clock_phandle_map = {}
    for node in all_nodes:
        if 'clock-controller' in node.name:
            clock_controllers.append(node)
            if node.attr.phandle != 0:
                clock_phandle_map[node.attr.phandle] = node

    for node in all_nodes:
        clock_lines = [l for l in node.content if 'clocks' in l and '=' in l]
        for cline in clock_lines:
            cl_str = cline.split('=')[1].strip().strip('<>;').replace(',','')
            cl_vals = cl_str.split()
            if cl_vals:
                val = cl_vals[0]
                if val.startswith("0x"):
                    cval = int(val,16)
                else:
                    cval = int(val)
                if cval in clock_phandle_map:
                    clock_relations.append((clock_phandle_map[cval], node))

    # 内存树解析
    # ---- 修改开始 (3.1) 如果memory_node没有找到，则查找以memory开头的节点 ----
    memory_node_found = False
    for node in all_nodes:
        if node.name == 'memory':
            memory_node = node
            memory_node_found = True
            break

    if not memory_node_found:
        for node in all_nodes:
            if node.name.startswith('memory'):
                memory_node = node
                memory_node_found = True
                break
    # ---- 修改结束 ----

    for node in all_nodes:
        if node.name == 'reserved-memory':
            for c in node.children:
                reserved_memory_nodes.append(c)

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

def get_current_dts_file():
    if 'selected_file' in session:
        sf = session['selected_file']
        if os.path.exists(sf):
            return sf
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

# 电源域页面
@app.route('/power_domain')
def power_domain():
    root = get_parsed_root()
    if not root:
        return "尚未选择或上传有效的 dts 文件", 400

    global power_domain_controllers, power_domain_relations

    # 构建电源域与挂载节点的关系
    controller_mapping = {}
    for controller in power_domain_controllers:
        controller_mapping[controller] = []

    for pd, node in power_domain_relations:
        controller_mapping[pd].append(node)

    # 按控制器名字排序
    sorted_controller_mapping = dict(sorted(controller_mapping.items(), key=lambda item: item[0].name.lower()))

    # 挂载节点按名字排序
    for controller in sorted_controller_mapping:
        sorted_controller_mapping[controller] = sorted(
            sorted_controller_mapping[controller], key=lambda node: node.name.lower()
        )

    # 为满足(2.2)要求，标记被多个电源域挂载的节点
    node_domain_counts = {}
    for controller, nodes in sorted_controller_mapping.items():
        for node in nodes:
            node_domain_counts.setdefault(node, 0)
            node_domain_counts[node] += 1

    # 生成颜色映射
    color_palette = ["#FFD700", "#ADFF2F", "#FF69B4", "#87CEFA", "#FFA07A"]
    node_color_map = {}
    color_index = 0
    for node, count in node_domain_counts.items():
        if count > 1:
            node_color_map[node] = color_palette[color_index % len(color_palette)]
            color_index += 1

    return render_template(
        'power_domain.html',
        controller_mapping=sorted_controller_mapping,
        node_color_map=node_color_map
    )

# 时钟树页面
@app.route('/clock_tree')
def clock_tree():
    root = get_parsed_root()
    if not root:
        return "尚未选择或上传有效的 dts 文件", 400

    global clock_controllers, clock_relations

    # 构建控制器与挂载节点的关系
    controller_mapping = {}
    for controller in clock_controllers:
        controller_mapping[controller] = []

    for cc, node in clock_relations:
        controller_mapping[cc].append(node)

    # 按控制器名字排序
    sorted_controller_mapping = dict(sorted(controller_mapping.items(), key=lambda item: item[0].name.lower()))

    # 挂载节点按名字排序
    for controller in sorted_controller_mapping:
        sorted_controller_mapping[controller] = sorted(
            sorted_controller_mapping[controller], key=lambda node: node.name.lower()
        )

    # 为每个控制器生成高亮颜色
    color_palette = ["#ADD8E6", "#90EE90", "#FFB6C1", "#FFA07A", "#D8BFD8"]
    node_color_map = {}
    for idx, controller in enumerate(sorted_controller_mapping.keys()):
        node_color_map[controller] = color_palette[idx % len(color_palette)]

    return render_template(
        'clock_tree.html',
        controller_mapping=sorted_controller_mapping,
        node_color_map=node_color_map
    )




def get_parsed_root():
    dts_file = get_current_dts_file()
    if not dts_file:
        return None
    return parse_dts_file(dts_file)

# 内存树页面
@app.route('/memory_tree')
def memory_tree():
    root = get_parsed_root()
    if not root:
        return "尚未选择或上传有效的 dts 文件", 400
    
    global memory_node, reserved_memory_nodes
    
    all_regions = []
    
    # 处理 memory_node
    if memory_node and memory_node.attr.regaddr and memory_node.attr.regsize:
        for i in range(len(memory_node.attr.regaddr)):
            all_regions.append({
                'address': memory_node.attr.regaddr[i],
                'size': memory_node.attr.regsize[i],
                'type': 'System Memory',
                'name': memory_node.name
            })
    
    # 处理 reserved_memory_nodes
    for rn in reserved_memory_nodes:
        if rn.attr.regaddr and rn.attr.regsize:
            for j in range(len(rn.attr.regaddr)):
                all_regions.append({
                    'address': rn.attr.regaddr[j],
                    'size': rn.attr.regsize[j],
                    'type': 'Reserved',
                    'name': rn.name
                })
        else:
            all_regions.append({
                'address': None,
                'size': None,
                'type': 'Reserved (No reg info)',
                'name': rn.name
            })

    # 排序函数
    def sort_key(x):
        if x['address'] is not None and x['size'] is not None:
            return x['address'] + x['size']
        return float('inf')  # 将没有地址或大小信息的项放到最后

    # 对 all_regions 进行排序
    all_regions.sort(key=sort_key)

    return render_template('memory_tree.html', 
                           memory_node=memory_node,
                           reserved_nodes=reserved_memory_nodes,
                           all_regions=all_regions)



if __name__ == '__main__':
    app.run(debug=True)
