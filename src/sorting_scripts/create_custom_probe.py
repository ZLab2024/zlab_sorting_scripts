"""Compatibility wrapper for the canonical probes generation/export API."""
from .probes import make_linear_probe, save_probe


def create_linear_probe(output, *, n_contacts=16, pitch_um=50.):
    """Write a new linear probe; use probes.make_linear_probe for in-memory use."""
    probe = make_linear_probe(n_contacts, pitch_um=pitch_um)
    save_probe(probe, output)
    return probe
