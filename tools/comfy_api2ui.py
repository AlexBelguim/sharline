"""Turn a ComfyUI API graph (what our scripts POST to /prompt) into an editor workflow you can open in ComfyUI.

  python tools/comfy_api2ui.py graph.api.json graph.ui.json

Widget order, seed controls ("fixed") and the image-upload widget come from the live /object_info, so ComfyUI must
be running. Nodes are laid out left to right by their depth in the graph.
"""
import json
import os
import sys
import urllib.request

COMFY = os.environ.get("COMFY_URL", "http://127.0.0.1:8188")
WIDGET_TYPES = {"INT", "FLOAT", "STRING", "BOOLEAN", "COMBO"}


def object_info():
    with urllib.request.urlopen(COMFY + "/object_info", timeout=120) as r:
        return json.loads(r.read())


def _is_widget(spec):
    t = spec[0]
    return isinstance(t, list) or t in WIDGET_TYPES


def _ordered_inputs(info):
    order = info.get("input_order") or {k: list(v) for k, v in info["input"].items()}
    out = []
    for sec in ("required", "optional"):
        for name in order.get(sec, []):
            out.append((name, info["input"][sec][name]))
    return out


def convert(api, info, title_by_id=None):
    title_by_id = title_by_id or {}
    ids = sorted(api, key=int)
    # depth = longest chain of links feeding the node -> x column
    depth = {}

    def d(nid):
        if nid not in depth:
            depth[nid] = 0
            srcs = [v[0] for v in api[nid]["inputs"].values() if isinstance(v, list) and len(v) == 2]
            depth[nid] = 1 + max((d(s) for s in srcs), default=-1)
        return depth[nid]

    for nid in ids:
        d(nid)
    col_y = {}
    nodes, links = [], []
    node_by_id = {}
    for order, nid in enumerate(sorted(ids, key=lambda n: (depth[n], int(n)))):
        n = api[nid]
        ni = info[n["class_type"]]
        widgets, inputs = [], []
        dyn = {k: v for k, v in n["inputs"].items() if "." in k}  # dynamic / autogrow inputs (images.image_1)
        for name, spec in _ordered_inputs(ni):
            val = n["inputs"].get(name)
            linked = isinstance(val, list) and len(val) == 2 and isinstance(val[0], str)
            if _is_widget(spec):
                default = spec[1].get("default") if len(spec) > 1 and isinstance(spec[1], dict) else None
                if isinstance(spec[0], list) and default is None and spec[0]:
                    default = spec[0][0]
                widgets.append(default if (linked or val is None) else val)
                opts = spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {}
                if opts.get("control_after_generate"):
                    widgets.append("fixed")
                if opts.get("image_upload"):
                    widgets.append("image")
                if linked:
                    inputs.append({"name": name, "type": spec[0] if isinstance(spec[0], str) else "COMBO",
                                   "widget": {"name": name}, "link": None, "_src": val})
            elif spec[0].startswith("COMFY_AUTOGROW"):
                for k, v in sorted(dyn.items()):
                    if k.startswith(name + "."):
                        inputs.append({"name": k, "type": "IMAGE", "link": None, "_src": v})
            else:
                inputs.append({"name": name, "type": spec[0], "link": None, "_src": val if linked else None})
        outs = [{"name": nm, "type": t, "links": []}
                for t, nm in zip(ni["output"], ni.get("output_name") or ni["output"])]
        x = 60 + depth[nid] * 420
        y = col_y.get(depth[nid], 60)
        h = 90 + 26 * (len(widgets) + len(inputs) + len(outs))
        if any(isinstance(w, str) and len(w) > 60 for w in widgets):
            h += 220
        col_y[depth[nid]] = y + h + 40
        node = {"id": int(nid), "type": n["class_type"], "pos": [x, y], "size": [380, h], "flags": {},
                "order": order, "mode": 0, "inputs": inputs, "outputs": outs,
                "properties": {"Node name for S&R": n["class_type"]}, "widgets_values": widgets}
        if nid in title_by_id:
            node["title"] = title_by_id[nid]
        nodes.append(node)
        node_by_id[int(nid)] = node
    lid = 0
    for node in nodes:
        for slot, inp in enumerate(node["inputs"]):
            src = inp.pop("_src")
            if not src:
                continue
            lid += 1
            s_node, s_slot = node_by_id[int(src[0])], src[1]
            t = s_node["outputs"][s_slot]["type"]
            links.append([lid, s_node["id"], s_slot, node["id"], slot, t])
            inp["link"] = lid
            s_node["outputs"][s_slot]["links"].append(lid)
    for node in nodes:
        for i, o in enumerate(node["outputs"]):
            o["slot_index"] = i
    return {"last_node_id": max(int(i) for i in ids), "last_link_id": lid, "nodes": nodes, "links": links,
            "groups": [], "config": {}, "extra": {"ds": {"scale": 0.7, "offset": [0, 0]}}, "version": 0.4}


if __name__ == "__main__":
    api = json.load(open(sys.argv[1], encoding="utf-8"))
    ui = convert(api, object_info())
    with open(sys.argv[2], "w", encoding="utf-8", newline="\n") as f:
        json.dump(ui, f, indent=1)
    print("wrote", sys.argv[2])
