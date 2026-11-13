"""Version-scoped launcher integration; installed GUI files remain untouched."""

from copy import deepcopy
from importlib.metadata import entry_points, version


def register_ensemble_view():
    from spikeinterface_gui.viewlist import possible_class_views

    installed = (version("spikeinterface"), version("spikeinterface-gui"))
    if installed != ("0.103.0", "0.11.0"):
        raise RuntimeError(
            f"Waveform ensemble integration supports SpikeInterface 0.103.0 / GUI 0.11.0; found {installed}. "
            "Review the version-specific selection adapter before using other versions."
        )
    from .waveform_ensemble import WaveformEnsembleView
    from .spike_snippets import SpikeSnippetsView

    entries = entry_points(group="spikeinterface_gui.views")
    for name, expected in (("waveformensemble", WaveformEnsembleView), ("spikesnippets", SpikeSnippetsView)):
        plugins = [ep for ep in entries if ep.name == name]
        if len(plugins) != 1:
            raise RuntimeError(
                f"{name} plugin registration is missing or duplicated. In this notebook's environment, "
                "run `python -m pip install --no-deps -e /path/to/zlab_sorting_script` "
                f"then restart the kernel. Expected one spikeinterface_gui.views:{name} entry point."
            )
        view_class = plugins[0].load()
        if view_class is not expected:
            raise RuntimeError(f"{name} entry point resolves to a different plugin. Check installed packages.")
        existing = possible_class_views.get(name)
        if existing is not None and existing is not view_class:
            raise RuntimeError(f"Another view already uses the {name} ID.")
        # GUI 0.11 has a registry but no entry-point discovery.
        possible_class_views[name] = view_class


def default_ensemble_layout():
    from spikeinterface_gui.layout_presets import default_layout

    layout = deepcopy(default_layout)
    # Separate adjacent lower docks keep templates and ensembles visible together.
    layout["zone3"].insert(0, "spikesnippets")
    layout["zone7"] = ["waveform", "waveformheatmap"]
    layout["zone8"] = ["waveformensemble", "correlogram", "isi", "mainsettings"]
    return layout


def launch_web_ensemble(analyzer, curation, kwargs):
    import panel as pn
    from spikeinterface_gui import run_mainwindow
    from spikeinterface_gui.backend_panel import start_server
    from spikeinterface_gui.curation_tools import empty_curation_data

    register_ensemble_view()
    options = dict(kwargs)
    if options.get("layout") is None and options.get("layout_preset") is None:
        options["layout"] = default_ensemble_layout()
    start_app = options.pop("start_app", True)
    address = options.pop("address", "localhost")
    port = options.pop("port", 0)
    server_options = options.pop("panel_start_server_kwargs", None) or {}

    def make_window():
        session_options = dict(options)
        for key in ("layout", "curation_dict", "label_definitions", "displayed_unit_properties",
                    "extra_unit_properties", "skip_extensions"):
            if options.get(key) is not None:
                session_options[key] = deepcopy(options[key])
        if curation:
            # GUI 0.11 shallow-copies its default curation dict. Supply a fresh
            # nested dictionary so browser sessions cannot share decision lists.
            if options.get("curation_dict") is None:
                session_options["curation_dict"] = deepcopy(empty_curation_data)
        return run_mainwindow(
            analyzer=analyzer, mode="web", curation=curation, start_app=False, **session_options,
        )

    # Construct eagerly: registration/layout errors should surface to the caller.
    window = make_window()
    if not start_app:
        return window
    first = [window]

    def session_layout():
        # Serve a factory, not a shared Panel object. Each browser session gets
        # its own controller, selection watchers, Bokeh sources, and cache.
        current = first.pop() if first else make_window()
        for name in ("waveformensemble", "spikesnippets"):
            if name in current.views:
                pn.state.on_session_destroyed(current.views[name].close)
        return current.main_layout

    start_server({"/": session_layout}, address=address, port=port, **server_options)
    return window
