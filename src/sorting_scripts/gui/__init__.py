"""Optional lab GUI launcher; no checkout or sibling-repository dependency."""

def launch_curation_gui(analyzer, *, mode: str = "web", curation: bool = True, **kwargs):
    """Launch the GUI, avoiding its Param class-docstring failure in IPython.

    Only automatic documentation generation is disabled during the web utility
    import. Param's original setting is restored even if that import fails.
    Web launches show adjacent waveform/ensemble panels and a spike snippet
    browser with centered Previous/Next navigation by default.
    Explicit layouts/presets are respected. See docs/waveform_ensemble.md.
    """
    if mode == "web":
        from importlib import import_module
        import param.parameterized as parameterized

        previous = parameterized.docstring_describe_params
        try:
            # SelectableTabulator overrides .param with an instance-only property.
            parameterized.docstring_describe_params = False
            import_module("spikeinterface_gui.utils_panel")
        finally:
            parameterized.docstring_describe_params = previous

        from ..ensemble_gui import launch_web_ensemble

        return launch_web_ensemble(analyzer, curation, kwargs)

    from spikeinterface_gui import run_mainwindow

    return run_mainwindow(analyzer=analyzer, mode=mode, curation=curation, **kwargs)
