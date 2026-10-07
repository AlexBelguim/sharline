"""Convert a ComfyUI *UI* workflow JSON (what the editor saves) into the *API* prompt format, resolve
constant switches, and prune nodes that no output depends on. Uses the server's /object_info for
widget names. Stdlib only.
"""
import json
import urllib.request

WIDGET_TYPES = {"INT", "FLOAT", "STRING", "BOOLEAN", "COMBO"}
FRONTEND_ONLY = {"Note", "MarkdownNote", "Reroute", "PrimitiveNode"}
CONTROL_VALUES = {"fixed", "randomize", "increment", "decrement"}


def object_info(url):
    with urllib.request.urlopen(url + "/object_info", timeout=120) as r:
        return json.loads(r.read())


def _is_widget(spec):
    t = spec[0]
    return isinstance(t, list) or t in WIDGET_TYPES


def convert(ui, info):
    nodes = {n["id"]: n for n in ui["nodes"]}
    links = {l[0]: l for l in ui["links"]}  # id -> [id, src, src_slot, dst, dst_slot, type]

    def resolve_src(link_id):
        l = links[link_id]
        src, slot = l[1], l[2]
        n = nodes[src]
        if n["type"] == "Reroute":  # follow reroutes upstream
            return resolve_src(n["inputs"][0]["link"])
        return [str(src), slot]

    api = {}
    for nid, n in nodes.items():
        if n["type"] in FRONTEND_ONLY or n.get("mode", 0) in (2, 4):
            continue
        spec = info.get(n["type"])
        if spec is None:
            raise KeyError(f"node type {n['type']} (#{nid}) unknown to server")
        linked = {i["name"]: i.get("link") for i in n.get("inputs", []) if i.get("link") is not None}
        # pure sockets (listed in the UI node without a widget) never consume widget values
        sockets = {i["name"] for i in n.get("inputs", []) if "widget" not in i}
        inputs = {}
        vals = list(n.get("widgets_values") or [])
        if isinstance(n.get("widgets_values"), dict):
            vals = []
            inputs.update({k: v for k, v in n["widgets_values"].items()})
        order = list(spec["input"].get("required", {}).items()) + list(spec["input"].get("optional", {}).items())
        state = {"vi": 0}

        def take():
            if state["vi"] < len(vals):
                state["vi"] += 1
                return True, vals[state["vi"] - 1]
            return False, None

        def consume(name, s):
            if name in sockets and not _is_widget(s):
                return
            ok, v = take()
            if not ok:
                return
            if name not in linked:
                inputs[name] = v
            if s[0] == "COMFY_DYNAMICCOMBO_V3":  # selected key, then that option's own widgets
                opt = next((o for o in s[1]["options"] if o["key"] == v), None)
                if opt:
                    for sec in ("required", "optional"):
                        for sub, ss in opt["inputs"].get(sec, {}).items():
                            consume(f"{name}.{sub}", ss)
                return
            opts = s[1] if len(s) > 1 and isinstance(s[1], dict) else {}
            if (opts.get("control_after_generate") or name in ("seed", "noise_seed")) and \
                    state["vi"] < len(vals) and vals[state["vi"]] in CONTROL_VALUES:
                state["vi"] += 1

        for name, s in order:
            if name not in sockets or _is_widget(s):
                consume(name, s)
            if name in linked:
                inputs[name] = resolve_src(linked[name])
        api[str(nid)] = {"class_type": n["type"], "inputs": inputs}
    return api


def set_input(api, node_id, name, value):
    api[str(node_id)]["inputs"][name] = value


def resolve_switches(api):
    """Replace ComfySwitchNode whose `switch` is a constant (or comes from a PrimitiveBoolean)."""
    changed = True
    while changed:
        changed = False
        for nid, n in list(api.items()):
            if n["class_type"] != "ComfySwitchNode":
                continue
            sw = n["inputs"].get("switch")
            if isinstance(sw, list):
                src = api.get(sw[0])
                if not src or src["class_type"] != "PrimitiveBoolean":
                    continue
                sw = src["inputs"]["value"]
            chosen = n["inputs"].get("on_true" if sw else "on_false")
            for m in api.values():
                for k, v in m["inputs"].items():
                    if isinstance(v, list) and v[0] == nid:
                        m["inputs"][k] = chosen
            del api[nid]
            changed = True
    return api


def prune(api, info, keep_outputs=None):
    """Drop nodes that no output node depends on. keep_outputs: restrict to these output node ids."""
    outs = [nid for nid, n in api.items() if info[n["class_type"]].get("output_node")]
    if keep_outputs is not None:
        outs = [o for o in outs if o in {str(k) for k in keep_outputs}]
    needed, stack = set(), list(outs)
    while stack:
        nid = stack.pop()
        if nid in needed or nid not in api:
            continue
        needed.add(nid)
        for v in api[nid]["inputs"].values():
            if isinstance(v, list) and len(v) == 2 and isinstance(v[0], str):
                stack.append(v[0])
    return {k: v for k, v in api.items() if k in needed}
