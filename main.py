#!/usr/bin/env python3
"""
Satellite Digital Twin - Main Entry Point

Mission Profile: 500km Sun-Synchronous Orbit
Reference: loads.md specification

Power Budget:
- Platform base load: 15W continuous
- Payload imaging: +40W (sunlight only, 10 min/orbit)
- Downlink: +30W (8 min/orbit, 50% sun/50% eclipse)
- ADCS momentum dump: +10W (sunlight only, 5 min/orbit)

Data Budget:
- Generation: 2 Gbit/orbit
- Downlink: 50 Mbps

Constraint:
- Battery State of Charge >= 20% (STRICT)

Usage:
    python main.py                      # Run simulation
    python main.py --dashboard          # Launch web interface
    python main.py --orbits 10          # Simulate 10 orbits
    python main.py --compliance         # Display compliance specification
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from satellite.state import SatelliteState, SatelliteConfig
from simulation.engine import Simulation
from simulation.policy import (
    LoadsMDCompliantPolicy,
    BasicPolicy, 
    PowerSavePolicy, 
    HighPerformancePolicy,
    CustomizablePolicy
)
from output.timeseries import TimeSeriesExporter
from output.visualization import Visualizer


def create_mission_config() -> SatelliteConfig:
    """
    Create spacecraft configuration per loads.md specification.
    
    Power Budget:
        Base: 15W continuous
        Imaging: +40W (sunlight, 10 min/orbit)
        Downlink: +30W (8 min/orbit)
        ADCS dump: +10W (sunlight, 5 min/orbit)
    
    Data Budget:
        Generation: 2 Gbit/orbit
        Downlink: 50 Mbps for 8 min
    
    Constraint:
        Battery SoC >= 20%
    """
    return SatelliteConfig(
        # Spacecraft
        mass_kg=50.0,
        
        # Orbit: 500 km SSO
        orbit_altitude_km=500.0,
        orbit_period_min=95.0,
        sunlight_duration_min=60.0,
        eclipse_duration_min=35.0,
        
        # Electrical Power System
        solar_panel_power_w=60.0,
        battery_capacity_wh=100.0,
        min_soc_percent=20.0,
        max_soc_percent=100.0,
        charge_efficiency=0.95,
        discharge_efficiency=0.95,
        
        # Power budget per loads.md
        base_load_w=15.0,
        imaging_load_w=40.0,
        downlink_load_w=30.0,
        adcs_dump_load_w=10.0,
        
        # Operations timing per loads.md
        imaging_duration_min=10.0,
        downlink_duration_min=8.0,
        adcs_dump_duration_min=5.0,
        downlink_sunlight_fraction=0.5,
        
        # Data budget per loads.md
        data_per_orbit_gbit=2.0,
        downlink_speed_mbps=50.0,
        max_data_storage_gb=100.0,
        
        # Operational windows (orbit angle)
        imaging_windows_theta=[[20.0, 60.0]],
        ground_pass_window_theta=(95.0, 125.0),
        adcs_dump_window_theta=(65.0, 85.0),
        
        # Simulation
        timestep_min=1.0,
        soc_safety_margin_percent=5.0
    )


def create_initial_state() -> SatelliteState:
    """Create nominal initial spacecraft state."""
    return SatelliteState(
        battery_level_percent=80.0,
        battery_energy_wh=80.0,
        battery_voltage_v=12.0,
        total_load_w=15.0,
        base_load_w=15.0,
        onboard_data_volume_gb=0.0,
        temperature_c=287.0,
        battery_health_percent=97.0
    )


def get_policy(name: str):
    """Get operations policy by identifier."""
    policies = {
        'compliant': LoadsMDCompliantPolicy(),
        'basic': BasicPolicy(),
        'power_save': PowerSavePolicy(),
        'high_performance': HighPerformancePolicy(),
        'customizable': CustomizablePolicy()
    }
    return policies.get(name, LoadsMDCompliantPolicy())


def run_simulation(
    orbits: int = 5,
    policy_name: str = 'compliant',
    export_path: str = None,
    show_plots: bool = True,
    verbose: bool = True
):
    """
    Execute mission simulation with loads.md compliance verification.
    """
    if verbose:
        print("=" * 72)
        print("SATELLITE DIGITAL TWIN - MISSION SIMULATION")
        print("Reference: loads.md specification")
        print("=" * 72)
    
    config = create_mission_config()
    initial_state = create_initial_state()
    policy = get_policy(policy_name)
    
    if verbose:
        print(f"\nMISSION PARAMETERS")
        print("-" * 40)
        print(f"  Orbit: {config.orbit_altitude_km} km SSO")
        print(f"  Period: {config.orbit_period_min} min")
        print(f"  Sunlight: {config.sunlight_duration_min} min")
        print(f"  Eclipse: {config.eclipse_duration_min} min")
        
        print(f"\nPOWER BUDGET (loads.md)")
        print("-" * 40)
        print(f"  Base load:    {config.base_load_w:5.1f} W continuous")
        print(f"  Imaging:     +{config.imaging_load_w:5.1f} W ({config.imaging_duration_min} min/orbit)")
        print(f"  Downlink:    +{config.downlink_load_w:5.1f} W ({config.downlink_duration_min} min/orbit)")
        print(f"  ADCS dump:   +{config.adcs_dump_load_w:5.1f} W ({config.adcs_dump_duration_min} min/orbit)")
        
        print(f"\nDATA BUDGET (loads.md)")
        print("-" * 40)
        print(f"  Generation: {config.data_per_orbit_gbit} Gbit/orbit")
        print(f"  Downlink:   {config.downlink_speed_mbps} Mbps")
        
        print(f"\nCONSTRAINTS")
        print("-" * 40)
        print(f"  Battery SoC >= {config.min_soc_percent}% [STRICT]")
        print(f"  Battery capacity: {config.battery_capacity_wh} Wh")
        
        print(f"\nSIMULATION CONFIG")
        print("-" * 40)
        print(f"  Policy: {policy.name}")
        print(f"  Duration: {orbits} orbits ({orbits * config.orbit_period_min:.0f} min)")
    
    # Execute simulation
    sim = Simulation(config, initial_state, policy)
    
    if verbose:
        print(f"\nExecuting simulation...")
    
    history = sim.run(duration_orbits=orbits)
    
    if verbose:
        print(f"Simulation complete. {len(history)} timesteps executed.")
    
    # Results
    summary = sim.get_summary()
    compliance = summary.get('compliance', {})
    
    if verbose:
        print(f"\nRESULTS SUMMARY")
        print("-" * 40)
        print(f"  Duration: {summary['total_time_min']:.1f} min ({summary['total_orbits']} orbits)")
        print(f"  Battery: min={summary['battery']['min']:.1f}%, max={summary['battery']['max']:.1f}%, avg={summary['battery']['avg']:.1f}%")
        print(f"  Load: max={summary['load']['max']:.1f} W, avg={summary['load']['avg']:.1f} W")
        print(f"  Data generated: {summary['data']['total_generated']:.3f} GB")
        print(f"  Data downlinked: {summary['data']['total_downlinked']:.3f} GB")
        
        print(f"\n20% SoC COMPLIANCE STATUS")
        print("-" * 40)
        print(f"  Minimum SoC: {compliance.get('min_soc_reached', 0):.1f}%")
        print(f"  Violations: {compliance.get('soc_violations', 0)}")
        if compliance.get('compliant', False):
            print(f"  Status: PASS - Battery maintained above 20%")
        else:
            print(f"  Status: FAIL - Battery dropped below 20%")
    
    # Export
    if export_path:
        export_dir = Path(export_path)
        export_dir.mkdir(parents=True, exist_ok=True)
        
        exporter = TimeSeriesExporter(history)
        exporter.to_csv(export_dir / "telemetry.csv")
        exporter.to_json(export_dir / "telemetry.json")
        
        import json
        with open(export_dir / "compliance_report.json", 'w') as f:
            json.dump(sim.get_compliance_report(), f, indent=2)
        
        if verbose:
            print(f"\nData exported to: {export_dir}")
        
        try:
            viz = Visualizer(history)
            viz.save_all_plots(export_dir, prefix="mission")
        except ImportError:
            pass
    
    if show_plots:
        try:
            viz = Visualizer(history)
            viz.plot_overview(show=True)
        except ImportError:
            if verbose:
                print("\nNote: matplotlib required for plots")
    
    return sim, history


def display_specification():
    """Display loads.md compliance specification."""
    print("=" * 72)
    print("LOADS.MD COMPLIANCE SPECIFICATION")
    print("=" * 72)
    
    print("\nPOWER BUDGET")
    print("-" * 50)
    print("Platform base load:      15 W continuous")
    print("Payload imaging:        +40 W (sunlight only, 10 min/orbit)")
    print("Downlink (high-rate):   +30 W (8 min/orbit, 50% sun/50% eclipse)")
    print("ADCS momentum dump:     +10 W (sunlight only, 5 min/orbit)")
    
    print("\nOPERATIONAL MODES")
    print("-" * 50)
    print("Base only:               15 W")
    print("Base + Imaging:          55 W")
    print("Base + Downlink:         45 W")
    print("Base + ADCS dump:        25 W")
    print("Peak (Imaging + ADCS):   65 W")
    
    print("\nDATA BUDGET")
    print("-" * 50)
    print("Data generation:     2 Gbit per orbit (0.25 GB)")
    print("Imaging duration:    10 minutes per orbit")
    print("Generation rate:     0.025 GB/min during imaging")
    print("Downlink rate:       50 Mbps")
    print("Downlink duration:   8 minutes per orbit")
    print("Downlink capacity:   3 GB per pass")
    
    print("\nCRITICAL CONSTRAINT")
    print("-" * 50)
    print("Battery State of Charge shall NEVER drop below 20%")
    print("Safety margin: Load shedding initiated at 25%")
    
    print("\nENERGY ANALYSIS (per orbit)")
    print("-" * 50)
    print("Sunlight (60 min @ 60W solar):     60.0 Wh generated")
    print("Eclipse (35 min @ 15W base):        8.75 Wh consumed")
    print("Imaging (10 min @ 55W):             9.17 Wh consumed")
    print("Downlink (8 min @ 45W):             6.0 Wh consumed")
    print("ADCS dump (5 min @ 25W):            2.08 Wh consumed")
    print("Net per orbit (nominal):           ~+34 Wh (charging)")


def launch_dashboard():
    """Launch the web-based mission control interface."""
    import subprocess
    dashboard_path = Path(__file__).parent / "output" / "dashboard.py"
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(dashboard_path)])


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Satellite Digital Twin - Mission Simulation",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('--dashboard', '-d', action='store_true',
                        help='Launch web interface')
    parser.add_argument('--orbits', '-o', type=int, default=5,
                        help='Number of orbits (default: 5)')
    parser.add_argument('--policy', '-p', 
                        choices=['compliant', 'basic', 'power_save', 'high_performance'],
                        default='compliant',
                        help='Operations policy (default: compliant)')
    parser.add_argument('--export', '-e', type=str,
                        help='Export directory')
    parser.add_argument('--no-plots', action='store_true',
                        help='Disable visualization')
    parser.add_argument('--quiet', '-q', action='store_true',
                        help='Suppress output')
    parser.add_argument('--compliance', '-c', action='store_true',
                        help='Display compliance specification')
    
    args = parser.parse_args()
    
    if args.compliance:
        display_specification()
        return
    
    if args.dashboard:
        print("Initializing mission control interface...")
        launch_dashboard()
        return
    
    run_simulation(
        orbits=args.orbits,
        policy_name=args.policy,
        export_path=args.export,
        show_plots=not args.no_plots,
        verbose=not args.quiet
    )


if __name__ == "__main__":
    main()
