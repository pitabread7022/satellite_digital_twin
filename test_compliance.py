#!/usr/bin/env python3
"""Test script for 20% SoC compliance verification."""

from satellite.state import SatelliteState, SatelliteConfig
from simulation.engine import Simulation
from simulation.policy import LoadsMDCompliantPolicy

def test_low_battery():
    """Test protection with low starting battery."""
    print("=" * 60)
    print("🔋 Low Battery Stress Test")
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
    
    print(f"\nStarted at: 35% SoC")
    print(f"Minimum reached: {summary['battery']['min']:.1f}%")
    print(f"Final SOC: {summary['battery']['final']:.1f}%")
    print(f"Violations (below 20%): {compliance['soc_violations']}")
    
    if compliance['compliant']:
        print("Status: ✅ COMPLIANT - Battery never dropped below 20%")
    else:
        print("Status: ❌ NON-COMPLIANT")
    
    # Show protection events
    events = sim.get_events()
    protection_events = [e for e in events if 'SHED' in e.event_type or 'SAFE' in e.event_type or 'LOW' in e.event_type]
    if protection_events:
        print(f"\nProtection events ({len(protection_events)}):")
        for e in protection_events[:10]:
            print(f"  {e.time_s/60:.0f}min @ {e.battery_soc:.1f}%: {e.description}")

def test_eclipse_survival():
    """Test that satellite survives eclipse without SoC violation."""
    print("\n" + "=" * 60)
    print("🌑 Eclipse Survival Test")
    print("=" * 60)
    
    config = SatelliteConfig()
    # Start at eclipse entry point with moderate battery
    state = SatelliteState(
        battery_level_percent=50.0,
        battery_energy_wh=50.0,
        orbit_angle_deg=110.0  # Near eclipse entry
    )
    
    sim = Simulation(config, state, LoadsMDCompliantPolicy())
    history = sim.run(duration_orbits=2)
    
    summary = sim.get_summary()
    
    print(f"\nStarted at: 50% SoC near eclipse")
    print(f"Minimum reached: {summary['battery']['min']:.1f}%")
    print(f"SOC violations: {summary['compliance']['soc_violations']}")
    
    # Find eclipse events
    events = sim.get_events()
    eclipse_events = [e for e in events if 'ECLIPSE' in e.event_type]
    for e in eclipse_events:
        print(f"  {e.time_s/60:.0f}min: {e.description}")

def test_load_budget():
    """Verify load budget matches loads.md."""
    print("\n" + "=" * 60)
    print("⚡ Load Budget Verification")
    print("=" * 60)
    
    config = SatelliteConfig()
    
    print(f"\nloads.md Specification:")
    print(f"  Base load:    15W  -> Config: {config.base_load_w}W {'✓' if config.base_load_w == 15.0 else '✗'}")
    print(f"  Imaging:     +40W  -> Config: {config.imaging_load_w}W {'✓' if config.imaging_load_w == 40.0 else '✗'}")
    print(f"  Downlink:    +30W  -> Config: {config.downlink_load_w}W {'✓' if config.downlink_load_w == 30.0 else '✗'}")
    print(f"  ADCS dump:   +10W  -> Config: {config.adcs_dump_load_w}W {'✓' if config.adcs_dump_load_w == 10.0 else '✗'}")
    
    print(f"\nTiming Budget:")
    print(f"  Imaging:    10 min/orbit -> Config: {config.imaging_duration_min} min {'✓' if config.imaging_duration_min == 10.0 else '✗'}")
    print(f"  Downlink:    8 min/orbit -> Config: {config.downlink_duration_min} min {'✓' if config.downlink_duration_min == 8.0 else '✗'}")
    print(f"  ADCS dump:   5 min/orbit -> Config: {config.adcs_dump_duration_min} min {'✓' if config.adcs_dump_duration_min == 5.0 else '✗'}")
    
    print(f"\nData Budget:")
    print(f"  Generation: 2 Gbit/orbit -> Config: {config.data_per_orbit_gbit} Gbit {'✓' if config.data_per_orbit_gbit == 2.0 else '✗'}")
    print(f"  Downlink:   50 Mbps      -> Config: {config.downlink_speed_mbps} Mbps {'✓' if config.downlink_speed_mbps == 50.0 else '✗'}")

def test_data_generation():
    """Verify data generation matches loads.md (2 Gbit per orbit)."""
    print("\n" + "=" * 60)
    print("💾 Data Budget Verification")
    print("=" * 60)
    
    config = SatelliteConfig()
    state = SatelliteState(battery_level_percent=80.0, battery_energy_wh=80.0)
    
    sim = Simulation(config, state, LoadsMDCompliantPolicy())
    history = sim.run(duration_orbits=5)
    
    summary = sim.get_summary()
    total_orbits = summary['total_orbits']
    total_generated = summary['data']['total_generated']
    
    expected_per_orbit = config.data_per_orbit_gbit / 8.0  # 0.25 GB
    expected_total = expected_per_orbit * (total_orbits + 1)  # +1 for partial orbit
    
    print(f"\nSimulated {total_orbits} complete orbits")
    print(f"Data generated: {total_generated:.3f} GB")
    print(f"Expected (2 Gbit/orbit): ~{expected_total:.3f} GB")
    print(f"Per orbit average: {total_generated/(total_orbits+1):.3f} GB (spec: 0.25 GB)")

if __name__ == "__main__":
    test_load_budget()
    test_data_generation()
    test_low_battery()
    test_eclipse_survival()
    
    print("\n" + "=" * 60)
    print("✅ All compliance tests completed")
    print("=" * 60)


