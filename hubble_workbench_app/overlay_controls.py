"""Per-image display settings for Explorer overlays."""
import math


def layer_settings(settings, key):
    value = settings.get(key, {}) if isinstance(settings, dict) else {}
    if not isinstance(value, dict):
        value = {}
    try:
        opacity = float(value.get('opacity', 1))
        if not math.isfinite(opacity):
            raise ValueError()
    except (TypeError, ValueError):
        opacity = 1
    return {'visible': bool(value.get('visible', True)), 'opacity': min(1, max(0, opacity))}


def ordered_overlays(overlays, keys):
    order = {key: index for index, key in enumerate(keys)}
    return sorted(overlays, key=lambda item: order.get(item['record']['key'], len(order)))


def move_layer(keys, key, direction):
    result = list(keys)
    if key not in result:
        return result
    index = result.index(key)
    target = max(0, min(len(result)-1, index+direction))
    result.insert(target, result.pop(index))
    return result


def show_overlay_controls(app):
    import tkinter as tk
    from tkinter import ttk
    window = getattr(app, 'overlay_controls_window', None)
    if window is not None and window.winfo_exists():
        window.lift()
        app.refresh_overlay_controls()
        return
    window = tk.Toplevel(app)
    app.overlay_controls_window = window
    window.title('Image overlay layers')
    window.geometry('650x340')
    ttk.Label(window, text='Layers are drawn bottom to top. Hidden images retain their coverage outlines.').pack(anchor='w', padx=10, pady=8)
    tree = ttk.Treeview(window, columns=('visible','opacity','source','band'), show='headings', selectmode='browse', height=8)
    for name,width in [('visible',60),('opacity',70),('source',110),('band',320)]:
        tree.heading(name,text=name.title());tree.column(name,width=width)
    tree.pack(fill='both',expand=True,padx=10)
    controls = ttk.Frame(window);controls.pack(fill='x',padx=10,pady=8)
    visible=tk.BooleanVar(value=True);opacity=tk.DoubleVar(value=1)
    ttk.Checkbutton(controls,text='Visible',variable=visible).pack(side='left')
    ttk.Label(controls,text='Opacity (0-1)').pack(side='left',padx=6)
    ttk.Spinbox(controls,from_=0,to=1,increment=.1,textvariable=opacity,width=5).pack(side='left')
    status=tk.StringVar(value='Load downloaded images with Show selected images in Explorer.')
    ttk.Label(window,textvariable=status,wraplength=620).pack(anchor='w',padx=10,pady=(0,8))
    keys=[]
    def refresh(selected=None):
        if not window.winfo_exists():
            return
        tree.delete(*tree.get_children());keys.clear()
        for item in ordered_overlays(getattr(app,'wizard_overlay_cache',[]),getattr(app,'wizard_overlay_keys',[])):
            record=item['record'];key=record['key'];keys.append(key)
            settings=layer_settings(getattr(app,'wizard_overlay_settings',{}),key)
            tree.insert('', 'end', iid=str(len(keys)-1), values=('Yes' if settings['visible'] else 'No',f"{settings['opacity']:.2f}",record['source'],record.get('display_label',record['band'])))
        if selected in keys:
            tree.selection_set(str(keys.index(selected)))
    app.refresh_overlay_controls=refresh
    def selection(event=None):
        if tree.selection():
            key=keys[int(tree.selection()[0])]
            settings=layer_settings(getattr(app,'wizard_overlay_settings',{}),key)
            visible.set(settings['visible']);opacity.set(settings['opacity'])
    tree.bind('<<TreeviewSelect>>',selection)
    def apply():
        if not tree.selection():
            status.set('Select an image layer first.');return
        try:
            amount=float(opacity.get())
            if not math.isfinite(amount) or not 0<=amount<=1:raise ValueError()
        except (ValueError,tk.TclError):
            status.set('Opacity must be a number between 0 and 1.');return
        key=keys[int(tree.selection()[0])]
        settings=getattr(app,'wizard_overlay_settings',{}).copy()
        settings[key]={'visible':visible.get(),'opacity':amount};app.wizard_overlay_settings=settings
        app.observatory_draw_current_mosaic();refresh(key)
        status.set('Layer updated. Global opacity also applies. Save the project to keep these settings.')
    def move(direction):
        if not tree.selection():return
        key=keys[int(tree.selection()[0])]
        app.wizard_overlay_keys=move_layer(app.wizard_overlay_keys,key,direction)
        app.observatory_draw_current_mosaic();refresh(key)
    ttk.Button(controls,text='Apply',command=apply).pack(side='left',padx=8)
    ttk.Button(controls,text='Lower',command=lambda:move(-1)).pack(side='left',padx=3)
    ttk.Button(controls,text='Raise',command=lambda:move(1)).pack(side='left',padx=3)
    refresh()
