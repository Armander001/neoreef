"""Batch photogrammetry for Metashape Pro.

RULE: modules here may import ``Metashape`` and ``neoreef.common`` only.
``discovery`` deliberately does not import ``Metashape`` so it can be unit
tested in a plain interpreter.

Target interpreter: the Python bundled with Metashape Pro (3.9). Keep syntax
3.9-compatible (no ``X | None``, no ``match``).
"""
