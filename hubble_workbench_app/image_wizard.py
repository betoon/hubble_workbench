"""Guided multi-archive image projects, with all UI updates on the Tk thread."""
import json
import queue
import threading
import time
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk

import numpy as np
from PIL import Image, ImageTk

from .archive_catalog import SOURCES, Cancelled, check_cancel, image_record, search_archive
from .archive_downloads import DownloadCache
from .rgb_recommendations import recommend_rgb
from .image_overlays import start_overlay_load
from .resolution_matching import show_resolution_controls, validate_resolution
from .archive_coverage import align_shared, display_footprints, fits_footprint, project_polygons
from .paths import DOWNLOAD_DIR, OUTPUT_DIR


def recommend_channels(records):
    """Compatibility entry point for metadata-ranked RGB suggestions."""
    return recommend_rgb(records)[0]


def size_summary(records):
    known = sum(float(r.get("size") or 0) for r in records)
    unknown = sum(not r.get("size") for r in records)
    text = f"{known/1e6:.1f} MB known/estimated"
    return text + (f"; {unknown} file size(s) unknown" if unknown else "")


class ImageWizardMixin:
    def build_image_wizard(self):
        self.wizard_records, self.wizard_channels = [], {}
        self.wizard_queue = queue.Queue()
        self.wizard_cancel_event = threading.Event()
        self.wizard_busy = False
        self.wizard_target = tk.StringVar(value=self.target_var.get())
        self.wizard_source = tk.StringVar(value="Pan-STARRS")
        self.wizard_field = tk.StringVar(value="5")
        self.wizard_pixels = tk.StringVar(value="512")
        self.wizard_shared = tk.BooleanVar(value=True)
        self.wizard_luminance_strength = tk.DoubleVar(value=0.5)
        self.wizard_status = tk.StringVar(value="Choose a source and target, then find images. No files download until you choose an action.")
        self.wizard_source_help = tk.StringVar(value=SOURCES["Pan-STARRS"])
        self.wizard_channel_text = tk.StringVar(value="No RGB channels assigned.")
        self.wizard_tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.insert(1,self.wizard_tab,text="Image Wizard")
        top = ttk.LabelFrame(self.wizard_tab, text="1. Find images", padding=8)
        top.pack(fill="x")
        for column,(label,var,width) in enumerate((("Target / RA, Dec",self.wizard_target,24),
                                                    ("Field width (arcmin)",self.wizard_field,8),
                                                    ("Cutout pixels",self.wizard_pixels,8))):
            ttk.Label(top,text=label).grid(row=0,column=column,sticky="w",padx=4)
            ttk.Entry(top,textvariable=var,width=width).grid(row=1,column=column,sticky="ew",padx=4)
        ttk.Label(top,text="Source").grid(row=0,column=3,sticky="w")
        source = ttk.Combobox(top,textvariable=self.wizard_source,values=list(SOURCES)+["Loaded Hubble/JWST"],state="readonly",width=22)
        source.grid(row=1,column=3,padx=4)
        source.bind("<<ComboboxSelected>>",lambda event:self.wizard_source_help.set(SOURCES.get(self.wizard_source.get(),"Import the current MAST Browser products, then choose channels here.")))
        self.wizard_find_button = ttk.Button(top,text="Find images",command=self.wizard_find)
        self.wizard_find_button.grid(row=1,column=4,padx=4)
        ttk.Label(top,textvariable=self.wizard_source_help,wraplength=850).grid(row=2,column=0,columnspan=5,sticky="w",pady=(6,0))
        top.columnconfigure(0,weight=1)
        body = ttk.PanedWindow(self.wizard_tab,orient="horizontal")
        body.pack(fill="both",expand=True,pady=8)
        left,right = ttk.Frame(body),ttk.Frame(body)
        body.add(left,weight=3)
        body.add(right,weight=2)
        ttk.Label(left,text="2. Review images and assign colors",style="Section.TLabel").pack(anchor="w")
        tree_frame=ttk.Frame(left)
        tree_frame.pack(fill="both",expand=True)
        self.wizard_tree=ttk.Treeview(tree_frame,columns=("source","band","size"),show="headings",selectmode="extended",height=9)
        for col,width in (("source",100),("band",150),("size",100)):
            self.wizard_tree.heading(col,text=col.title())
            self.wizard_tree.column(col,width=width,minwidth=60)
        self.wizard_tree.pack(side="left",fill="both",expand=True)
        scroll=ttk.Scrollbar(tree_frame,orient="vertical",command=self.wizard_tree.yview)
        scroll.pack(side="right",fill="y")
        self.wizard_tree.configure(yscrollcommand=scroll.set)
        self.wizard_tree.bind("<<TreeviewSelect>>",lambda event:self.wizard_review())
        actions=ttk.Frame(left)
        actions.pack(fill="x",pady=6)
        self.wizard_action_buttons=[]
        for label,command in (("Suggest RGB",self.wizard_suggest),("Use as R",lambda:self.wizard_assign("red")),
                              ("Use as G",lambda:self.wizard_assign("green")),("Use as B",lambda:self.wizard_assign("blue")),
                              ("Use as L",lambda:self.wizard_assign("luminance")),("Clear L",self.wizard_clear_luminance)):
            button=ttk.Button(actions,text=label,command=command)
            button.pack(side="left",padx=2)
            self.wizard_action_buttons.append(button)
        ttk.Label(left,textvariable=self.wizard_channel_text,wraplength=500).pack(anchor="w")
        self.wizard_canvas=tk.Canvas(right,height=210,background="#101827",highlightthickness=0)
        self.wizard_canvas.pack(fill="both",expand=True)
        self.wizard_canvas.bind("<Configure>",lambda event:self.wizard_draw_coverage())
        self.wizard_report=tk.Text(right,height=7,wrap="word",state="disabled",font=("Segoe UI",9))
        self.wizard_report.pack(fill="x",pady=(5,0))
        bottom=ttk.LabelFrame(self.wizard_tab,text="3. Download, align and create",padding=8)
        bottom.pack(side="bottom",fill="x",before=body)
        ttk.Checkbutton(bottom,text="Crop to shared sky coverage (recommended for RGB)",variable=self.wizard_shared).pack(anchor="w")
        options_row=ttk.Frame(bottom)
        options_row.pack(fill="x")
        ttk.Button(options_row,text="Resolution matching...",command=lambda:show_resolution_controls(self)).pack(side="left")
        luminance_row=ttk.Frame(bottom)
        luminance_row.pack(fill="x")
        ttk.Label(luminance_row,text="Luminance strength (0-1; optional L band):").pack(side="left")
        ttk.Spinbox(luminance_row,from_=0,to=1,increment=.1,width=5,textvariable=self.wizard_luminance_strength).pack(side="left",padx=6)
        ttk.Label(luminance_row,text="Rebuild after changing strength. Display enhancement, not photometry.").pack(side="left")
        row=ttk.Frame(bottom)
        row.pack(fill="x",pady=4)
        for label,command in (("Preview selected",self.wizard_preview),("Download selected",self.wizard_download),
                              ("Build RGB / LRGB",self.wizard_build),("Save project",self.save_project_file),
                              ("Open project",self.open_project_file),("Export portable",self.export_portable_project)):
            button=ttk.Button(row,text=label,command=command)
            button.pack(side="left",padx=2)
            self.wizard_action_buttons.append(button)
        self.wizard_stop_button=ttk.Button(row,text="Stop",command=self.wizard_stop,state="disabled")
        self.wizard_stop_button.pack(side="right")
        self.wizard_progress=ttk.Progressbar(bottom,mode="determinate",maximum=100)
        self.wizard_progress.pack(fill="x",pady=4)
        ttk.Label(bottom,textvariable=self.wizard_status,wraplength=900,justify="left").pack(anchor="w")
        overlay_button = ttk.Button(options_row, text="Show selected images in Explorer", command=lambda: start_overlay_load(self))
        overlay_button.pack(side="left", padx=8)
        self.wizard_action_buttons.append(overlay_button)
        self.after(100,self.wizard_pump)

    def wizard_pump(self):
        try:
            while True:
                kind,value=self.wizard_queue.get_nowait()
                if kind=="progress":
                    percent,message=value
                    self.wizard_status.set(message)
                    if percent is not None:
                        self.wizard_progress.configure(value=percent)
                else:
                    self.wizard_busy=False
                    self.wizard_find_button.configure(state="normal")
                    for button in self.wizard_action_buttons:
                        button.configure(state="normal")
                    self.wizard_stop_button.configure(state="disabled")
                    if kind=="error":
                        self.wizard_status.set(str(value))
                    else:
                        callback,result=value
                        try:
                            callback(result)
                        except Exception as exc:
                            self.wizard_status.set(f"Could not finish this step: {exc}")
        except queue.Empty:
            pass
        self.after(100,self.wizard_pump)

    def wizard_start(self, work, finish):
        if self.wizard_busy:
            return
        self.wizard_busy=True
        self.wizard_cancel_event=threading.Event()
        self.wizard_find_button.configure(state="disabled")
        for button in self.wizard_action_buttons:
            button.configure(state="disabled")
        self.wizard_stop_button.configure(state="normal")
        self.wizard_progress.configure(value=0)
        self.wizard_status.set("Working...")
        event=self.wizard_cancel_event
        def worker():
            try:
                result=work(event)
                check_cancel(event)
                self.wizard_queue.put(("finished",(finish,result)))
            except Exception as exc:
                self.wizard_queue.put(("error",str(exc)))
        threading.Thread(target=worker,daemon=True).start()

    def wizard_stop(self):
        self.wizard_cancel_event.set()
        self.wizard_status.set("Stopping; a pending archive response may take up to its network timeout. Verified files are kept.")

    def wizard_find(self):
        target,source=self.wizard_target.get().strip(),self.wizard_source.get()
        try:
            field,pixels=float(self.wizard_field.get()),int(self.wizard_pixels.get())
        except ValueError:
            self.wizard_status.set("Enter a numeric field width and pixel count.")
            return
        if source=="Loaded Hubble/JWST":
            records=[]
            for row in self.product_results:
                if not self.product_is_direct_fits(row) or self.product_is_spectrum(row):
                    continue
                uri=str(row.get("dataURI", "") or row.get("dataURL", ""))
                if not uri:
                    continue
                from urllib.parse import urlencode
                url="https://mast.stsci.edu/api/v0.1/Download/file?"+urlencode({"uri":uri}) if uri.startswith("mast:") else uri
                records.append(image_record(row.get("obs_collection", "MAST"),self.target_var.get(),
                                            row.get("filters", "") or row.get("Spectral_Elt", ""),url,
                                            channel=self.product_rgb_channel(row),size=row.get("size"),
                                            region=row.get("s_region", ""),footprint_kind="archive polygon" if row.get("s_region") else "unknown",
                                            instrument=row.get("instrument_name", ""),key=uri))
            self.wizard_found((self.target_var.get(),records))
            return
        def work(cancel):
            records=search_archive(source,target,field,pixels,cancel,
                                   lambda message:self.wizard_queue.put(("progress",(None,message))))
            return target,records
        self.wizard_start(work,self.wizard_found)

    def wizard_found(self,result):
        target,records=result
        if self.wizard_records and getattr(self,"wizard_catalog_target",self.wizard_records[0]["target"]).lower()!=target.lower():
            self.wizard_records,self.wizard_channels=[],{}
            self.wizard_overlay_generation = getattr(self, 'wizard_overlay_generation', 0)+1
            self.wizard_overlay_cache = []
            self.wizard_overlay_keys = []
            self.wizard_overlay_settings = {}
            self.wizard_resolution = {}
            self.wizard_overlay_render_key = None
        self.wizard_catalog_target=target
        known={r["key"] for r in self.wizard_records}
        for record in records:
            if record["key"] not in known:
                self.wizard_records.append(record)
                known.add(record["key"])
        self.wizard_refresh()
        self.wizard_status.set(f"Found {len(records)} images; {len(self.wizard_records)} in this project. Select rows to review footprints and sizes.")

    def wizard_refresh(self):
        self.wizard_tree.delete(*self.wizard_tree.get_children())
        for index,record in enumerate(self.wizard_records):
            size=float(record.get("size") or 0)
            size_text=f"{'~' if record.get('size_estimated') else ''}{size/1e6:.1f} MB" if size else "Unknown"
            self.wizard_tree.insert("","end",iid=str(index),values=(record["source"],record.get("display_label",record["band"]),size_text))
        self.wizard_channel_text.set(" | ".join(f"{ch[0].upper()}: {r['source']} {r['band']}" for ch,r in self.wizard_channels.items()) or "No RGB channels assigned.")
        self.wizard_review()

    def wizard_selected(self):
        return [self.wizard_records[int(i)] for i in self.wizard_tree.selection()]

    def wizard_assign(self,channel):
        selected=self.wizard_selected()
        if len(selected)!=1:
            self.wizard_status.set("Select exactly one image to assign a color.")
            return
        self.wizard_channels[channel]=selected[0]
        self.wizard_channel_text.set(" | ".join(f"{ch[0].upper()}: {r['source']} {r['band']}" for ch,r in self.wizard_channels.items()))
        self.wizard_review()

    def wizard_clear_luminance(self):
        self.wizard_channels.pop("luminance", None)
        self.wizard_refresh()
        self.wizard_status.set("Luminance cleared. Rebuild for ordinary RGB.")

    def wizard_suggest(self):
        selected=self.wizard_selected() or self.wizard_records
        channels, explanation=recommend_rgb(selected)
        if not channels:
            self.wizard_status.set(explanation)
            return
        if "luminance" in self.wizard_channels:
            channels["luminance"] = self.wizard_channels["luminance"]
        self.wizard_channels=channels
        indices=[str(self.wizard_records.index(r)) for r in channels.values()]
        self.wizard_tree.selection_set(indices)
        self.wizard_channel_text.set(" | ".join(f"{ch[0].upper()}: {r['source']} {r['band']}" for ch,r in channels.items()))
        self.wizard_status.set(explanation)
        self.wizard_review()

    def wizard_review(self):
        selected=self.wizard_selected()
        messages=[f"Selected: {len(selected)} image(s). {size_summary(selected)}."]
        for record,polygons,kind in display_footprints(selected):
            messages.append(f"{record['source']} / {record['band']}: {kind if polygons else 'coverage unknown until downloaded'}.")
        if len({r["source"] for r in self.wizard_channels.values()})>1:
            messages.append("Manual multiwavelength mapping: colors represent different observatories, not natural optical color.")
        messages.append("Outlined requested fields show your cutout request, not measured detector coverage. FITS footprints appear after download; valid-pixel overlap is checked during alignment.")
        self.wizard_report.configure(state="normal")
        self.wizard_report.delete("1.0","end")
        self.wizard_report.insert("1.0","\n".join(messages))
        self.wizard_report.configure(state="disabled")
        self.wizard_draw_coverage()

    def wizard_draw_coverage(self):
        canvas=self.wizard_canvas
        canvas.delete("all")
        selected=self.wizard_selected()[:30]
        entries=[]
        for record,polygons,kind in display_footprints(selected):
            entries.extend((record,polygon,kind) for polygon in polygons
                           if len(polygon)>=3 and np.isfinite(np.asarray(polygon)).all())
        if not entries:
            canvas.create_text(15,20,anchor="nw",text="Select images to see available sky footprints.\nUnknown coverage is not drawn.",fill="white")
            return
        projected=project_polygons([e[1] for e in entries])
        flat=np.concatenate(projected)
        low,high=flat.min(axis=0),flat.max(axis=0)
        span=np.maximum(high-low,1e-8)
        width,height=max(100,canvas.winfo_width()),max(100,canvas.winfo_height())
        scale=min((width-40)/span[0],(height-50)/span[1])
        colors=("#62b6ff","#f4bf60","#76dcac","#f28fce","#c0abff")
        for index,((record,polygon,kind),points) in enumerate(zip(entries,projected)):
            xy=np.column_stack((width-20-(points[:,0]-low[0])*scale,height-20-(points[:,1]-low[1])*scale))
            color=colors[index%len(colors)]
            canvas.create_polygon(*xy.flatten(),fill="",outline=color,width=2,dash=(4,3) if kind=="requested field" else ())
        canvas.create_text(10,8,anchor="nw",fill="white",text="Sky coverage: north up, east left • dashed = requested field")

    def wizard_fetch_records(self,records,cancel):
        cache=DownloadCache(DOWNLOAD_DIR/"archive_cache")
        paths=[]
        last=[0.0]
        try:
            for index,record in enumerate(records):
                def progress(done,total,message):
                    if time.monotonic()-last[0] < .15 and done!=total:
                        return
                    last[0]=time.monotonic()
                    percent=100*(index+(done/total if total else 0))/max(1,len(records))
                    detail=f"{message}: {record['source']} {record['band']} — {done/1e6:.1f} MB"+(f" / {total/1e6:.1f} MB" if total else "")
                    self.wizard_queue.put(("progress",(percent,detail)))
                path=cache.fetch(record,cancel,progress)
                updated=dict(record,local_path=str(path))
                try:
                    updated["footprints"]=[fits_footprint(path)]
                except Exception:
                    pass
                paths.append(updated)
        finally:
            cache.session.close()
        return paths

    def wizard_merge_downloads(self,records):
        by_key={record["key"]:record for record in records}
        self.wizard_records=[by_key.get(r["key"],r) for r in self.wizard_records]
        self.wizard_channels={ch:by_key.get(r["key"],r) for ch,r in self.wizard_channels.items()}
        self.wizard_refresh()
        self.wizard_tree.selection_set([str(i) for i,r in enumerate(self.wizard_records) if r["key"] in by_key])
        self.wizard_review()

    def wizard_download(self):
        records=[dict(r) for r in self.wizard_selected()]
        if not records:
            self.wizard_status.set("Select one or more images first.")
            return
        self.wizard_start(lambda cancel:self.wizard_fetch_records(records,cancel),self.wizard_downloaded)

    def wizard_downloaded(self,records):
        self.wizard_merge_downloads(records)
        self.wizard_status.set(f"Verified {len(records)} downloads. FITS footprints are ready for review.")

    def wizard_preview(self):
        records=self.wizard_selected()
        if len(records)!=1:
            self.wizard_status.set("Select one image to preview.")
            return
        def work(cancel):
            downloaded=self.wizard_fetch_records([dict(records[0])],cancel)
            from .fits_io import first_image_hdu
            from .image_processing import normalize_image
            data,header=first_image_hdu(downloaded[0]["local_path"])
            step=max(1,int(np.ceil(max(data.shape)/800)))
            preview=Image.fromarray(normalize_image(data[::step,::step]),mode="L")
            return downloaded,preview
        def finish(result):
            records,preview=result
            self.wizard_merge_downloads(records)
            window=tk.Toplevel(self)
            window.title(f"{records[0]['source']} — {records[0]['band']}")
            photo=ImageTk.PhotoImage(preview)
            label=ttk.Label(window,image=photo)
            label.image=photo
            label.pack()
            ttk.Label(window,text=f"{records[0]['target']} | {records[0]['source']} | {records[0]['band']}").pack(pady=6)
            self.wizard_status.set("Preview ready. This single-band stretch is for display.")
        self.wizard_start(work,finish)

    def wizard_build(self):
        if not {"red","green","blue"}.issubset(self.wizard_channels):
            self.wizard_status.set("Assign R, G and B, or choose Suggest RGB first.")
            return
        channel_order=["red","green","blue"]
        strength = 0.0
        if "luminance" in self.wizard_channels:
            try:
                strength = float(self.wizard_luminance_strength.get())
                if not np.isfinite(strength) or not 0 <= strength <= 1:
                    raise ValueError()
            except (ValueError, tk.TclError):
                self.wizard_status.set("Luminance strength must be a number between 0 and 1.")
                return
            channel_order.append("luminance")
        settings=getattr(self,"wizard_resolution",{})
        resolution=None
        if settings.get("enabled"):
            try:
                resolution=validate_resolution([settings.get(ch, "") for ch in channel_order],len(channel_order))
            except ValueError:
                self.wizard_status.set("Set positive RGB/L FWHM values in Resolution matching first.")
                return
        records=[dict(self.wizard_channels[ch]) for ch in channel_order]
        shared=self.wizard_shared.get()
        target=self.wizard_target.get()
        run=OUTPUT_DIR/("archive_project_"+datetime.now().strftime("%Y%m%d_%H%M%S_%f"))
        def work(cancel):
            downloaded=self.wizard_fetch_records(records,cancel)
            self.wizard_queue.put(("progress",(None,"Aligning sky coordinates and measuring shared coverage...")))
            paths,metadata=align_shared([r["local_path"] for r in downloaded],run,shared,cancel,resolution=resolution)
            if len(channel_order) == 4 and metadata["overlap_fraction"] <= 0:
                raise ValueError("The luminance image and RGB images have no common sky coverage.")
            return downloaded,paths,metadata
        def finish(result):
            downloaded,paths,metadata=result
            self.wizard_merge_downloads(downloaded)
            self.target_var.set(target)
            for var,path in zip((self.red_path_var,self.green_path_var,self.blue_path_var),paths):
                var.set(path)
            self.high_quality_var.set(True)
            self.use_fits_liberator_var.set(False)
            self.mosaic_coverage_mode_var.set("Full mosaic")
            self.presentation_cleanup_var.set(False)
            self.archive_provenance={"run_directory":str(run),"target":target,"sources":downloaded,
                                     "channel_order":channel_order,"alignment":metadata,"aligned_paths":paths,
                                     "luminance":{"strength":strength} if len(channel_order)==4 else {},
                                     "color_mapping":"display false color; not calibrated photometry"}
            (run/"project.json").write_text(json.dumps(self.project_state(),indent=2),encoding="utf-8")
            self.wizard_status.set(f"Aligned; {metadata['overlap_fraction']:.1%} common overlap before cropping. Project saved. Composing RGB...")
            self.notebook.select(self.compose_tab)
            self.compose_async()
        self.wizard_start(work,finish)

    def wizard_state(self):
        return {"resolution":getattr(self,"wizard_resolution",{}),"target":self.wizard_target.get(),"source":self.wizard_source.get(),
                "field_arcmin":self.wizard_field.get(),"pixels":self.wizard_pixels.get(),
                "shared":self.wizard_shared.get(),"luminance_strength":self.wizard_luminance_strength.get(),"records":self.wizard_records,"channels":self.wizard_channels,
                "catalog_target":getattr(self,"wizard_catalog_target",self.wizard_target.get())}

    def wizard_restore(self,data):
        self.wizard_resolution=dict(data.get("resolution") or {})
        self.wizard_target.set(data.get("target",""))
        self.wizard_source.set(data.get("source","Pan-STARRS"))
        self.wizard_field.set(data.get("field_arcmin","5"))
        self.wizard_pixels.set(data.get("pixels","512"))
        self.wizard_shared.set(data.get("shared",True))
        self.wizard_luminance_strength.set(data.get("luminance_strength",0.5))
        self.wizard_records=data.get("records",[])
        self.wizard_channels=data.get("channels",{})
        self.wizard_catalog_target=data.get("catalog_target",data.get("target",""))
        self.wizard_source_help.set(SOURCES.get(self.wizard_source.get(),"Import current MAST Browser products."))
        self.wizard_refresh()
