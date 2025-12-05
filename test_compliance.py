#!/usr/bin/env python3
"""
Compliance Verification Test Suite

Verifies satellite digital twin compliance with loads.md specification:
- Power budget adherence
- Data budget adherence  
- 20% State of Charge constraint
"""

from satellite.state import SatelliteState, SatelliteConfig
from simulation.engine import Simulation
from simulation.policy import LoadsMDCompliantPolicy


def test_load_budget():
    """Verify load budget matches loads.md specification."""
    print("=" * 60)
    print("LOAD BUDGET VERIFICATION")
    print("=" * 60)
    
    config = SatelliteConfig()
    
    print(f"\nloads.md Specification vs Configuration:")
    print(f"  Base load:    15 W  -> {config.base_load_w} W {'[PASS]' if config.base_load_w == 15.0 else '[FAIL]'}")
    print(f"  Imaging:     +40 W  -> {config.imaging_load_w} W {'[PASS]' if config.imaging_load_w == 40.0 else '[FAIL]'}")
    print(f"  Downlink:    +30 W  -> {config.downlink_load_w} W {'[PASS]' if config.downlink_load_w == 30.0 else '[FAIL]'}")
    print(f"  ADCS dump:   +10 W  -> {config.adcs_dump_load_w} W {'[PASS]' if config.adcs_dump_load_w == 10.0 else '[FAIL]'}")
    
    print(f"\nTiming Budget:")
    print(f"  Imaging:    10 min/orbit -> {config.imaging_duration_min} min {'[PASS]' if config.imaging_duration_min == 10.0 else '[FAIL]'}")
    print(f"  Downlink:    8 min/orbit -> {config.downlink_duration_min} min {'[PASS]' if config.downlink_duration_min == 8.0 else '[FAIL]'}")
    print(f"  ADCS dump:   5 min/orbit -> {config.adcs_dump_duration_min} min {'[PASS]' if config.adcs_dump_duration_min == 5.0 else '[FAIL]'}")
    
    print(f"\nData Budget:")
    print(f"  Generation: 2 Gbit/orbit -> {config.data_per_orbit_gbit} Gbit {'[PASS]' if config.data_per_orbit_gbit == 2.0 else '[FAIL]'}")
    print(f"  Downlink:   50 Mbps      -> {config.downlink_speed_mbps} Mbps {'[PASS]' if config.downlink_speed_mbps == 50.0 else '[FAIL]'}")


def test_data_generation():
    """Verify data generation matches loads.md specification."""
    print("\n" + "=" * 60)
    print("DATA BUDGET VERIFICATION")
    print("=" * 60)
    
    config = SatelliteConfig()
    state = SatelliteState(battery_level_percent=80.0, battery_energy_wh=80.0)
    
    sim = Simulation(config, state, LoadsMDCompliantPolicy())
    history = sim.run(duration_orbits=5)
    
    summary = sim.get_summary()
    total_orbits = summary['total_orbits']
    total_generated = summary['data']['total_generated']
    
    expected_per_orbit = config.data_per_orbit_gbit / 8.0
    
    print(f"\nSimulation: {total_orbits} complete orbits")
    print(f"Data generated: {total_generated:.3f} GB")
    print(f"Expected (2 Gbit/orbit): {expected_per_orbit * (total_orbits + 1):.3f} GB")
    print(f"Per orbit average: {total_generated/(total_orbits+1):.3f} GB (spec: 0.25 GB)")


def test_low_battery_protection():
    """Verify 20% SoC protection with low starting battery."""
    print("\n" + "=" * 60)
    print("LOW BATTERY STRESS TEST")
    print("=" * 60)
    
    config = SatelliteConfig()
    state = SatelliteState(
        battery_level_percent=35.0,
        battery_energy_wh=35.0
    )
    
    sim = Simulation(config, state, LoadsMDCompliantPolicy())
    history = sim.run(duration_orbits=3)
    
    summary = sim.get_summary()
    compliance = summary['compliance']
    
    print(f"\nInitial SoC: 35%")
    print(f"Minimum SoC: {summary['battery']['min']:.1f}%")
    print(f"Final SoC: {summary['battery']['final']:.1f}%")
    print(f"Violations: {compliance['soc_violations']}")
    
    if compliance['compliant']:
        print("Status: [PASS] Battery maintained above 20%")
    else:
        print("Status: [FAIL] Battery dropped below 20%")
    
    events = sim.get_events()
    protection_events = [e for e in events if 'SHED' in e.event_type or 'SAFE' in e.event_type or 'LOW' in e.event_type]
    if protection_events:
        print(f"\nProtection events ({len(protection_events)}):")
        for e in protection_events[:10]:
            print(f"  T+{e.time_s/60:.0f}m @ {e.battery_soc:.1f}%: {e.description}")


def test_eclipse_survival():
    """Verify spacecraft survives eclipse without SoC violation."""
    print("\n" + "=" * 60)
    print("ECLIPSE SURVIVAL TEST")
    print("=" * 60)
    
    config = SatelliteConfig()
    state = SatelliteState(
        battery_level_percent=50.0,
        battery_energy_wh=50.0,
        orbit_angle_deg=110.0
    )
    
    sim = Simulation(config, state, LoadsMDCompliantPolicy())
    history = sim.run(duration_orbits=2)
    
    summary = sim.get_summary()
    
    print(f"\nInitial SoC: 50% (near eclipse entry)")
    print(f"Minimum SoC: {summary['battery']['min']:.1f}%")
    print(f"Violations: {summary['compliance']['soc_violations']}")
    
    events = sim.get_events()
    eclipse_events = [e for e in events if 'ECLIPSE' in e.event_type]
    for e in eclipse_events:
        print(f"  T+{e.time_s/60:.0f}m: {e.description}")


def test_nominal_operations():
    """Verify nominal operations over extended duration."""
    print("\n" + "=" * 60)
    print("NOMINAL OPERATIONS TEST")
    print("=" * 60)
    
    config = SatelliteConfig()
    state = SatelliteState(battery_level_percent=80.0, battery_energy_wh=80.0)
    
    sim = Simulation(config, state, LoadsMDCompliantPolicy())
    history = sim.run(duration_orbits=10)
    
    summary = sim.get_summary()
    compliance = summary['compliance']
    
    print(f"\nDuration: {summary['total_time_min']:.0f} min ({summary['total_orbits']} orbits)")
    print(f"Battery range: {summary['battery']['min']:.1f}% - {summary['battery']['max']:.1f}%")
    print(f"Average load: {summary['load']['avg']:.1f} W")
    print(f"Data generated: {summary['data']['total_generated']:.3f} GB")
    print(f"Data downlinked: {summary['data']['total_downlinked']:.3f} GB")
    print(f"Events: {summary['events_count']}")
    
    if compliance['compliant']:
        print("\n20% SoC Compliance: [PASS]")
    else:
        print("\n20% SoC Compliance: [FAIL]")


if __name__ == "__main__":
    test_load_budget()
    test_data_generation()
    test_low_battery_protection()
    test_eclipse_survival()
    test_nominal_operations()
    
    print("\n" + "=" * 60)
    print("COMPLIANCE VERIFICATION COMPLETE")
    print("=" * 60)
