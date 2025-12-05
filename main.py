#!/usr/bin/env python3
"""
Satellite Digital Twin - Main Entry Point

Compliant with loads.md specification:
- Platform base load: 15W continuous
- Payload imaging: +40W (sunlight only, 10 min/orbit)
- Downlink: +30W (8 min/orbit, 50% sun/50% eclipse)
- ADCS momentum dump: +10W (sunlight only, 5 min/orbit)
- Data: 2 Gbit/orbit generated, 50 Mbps downlink
- Battery SoC: NEVER drops below 20%

Usage:
    python main.py                      # Run simulation
    python main.py --dashboard          # Launch Streamlit dashboard
    python main.py --orbits 10          # Run for 10 orbits
    python main.py --policy basic       # Use basic policy
    python main.py --compliance         # Show compliance report
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


def create_loads_md_config() -> SatelliteConfig:
    """
    Create configuration strictly per loads.md specification.
    
    Load Budget:
    - Base: 15W continuous
    - Imaging: +40W (sunlight, 10 min/orbit)
    - Downlink: +30W (8 min/orbit)
    - ADCS dump: +10W (sunlight, 5 min/orbit)
    
    Data Budget:
    - 2 Gbit/orbit generated
    - 50 Mbps downlink for 8 min
    
    Constraint:
    - Battery SoC >= 20%
    """
    return SatelliteConfig(
        # Satellite
        mass_kg=50.0,
        
        # Orbit: 500 km SSO
        orbit_altitude_km=500.0,
        orbit_period_min=95.0,
        sunlight_duration_min=60.0,
        eclipse_duration_min=35.0,
        
        # EPS
        solar_panel_power_w=60.0,
        battery_capacity_wh=100.0,
        min_soc_percent=20.0,  # STRICT: Never below 20%
        max_soc_percent=100.0,
        charge_efficiency=0.95,
        discharge_efficiency=0.95,
        
        # Load budget per loads.md
        base_load_w=15.0,  # Platform base (ADCS, OBC, COMMS idle)
        imaging_load_w=40.0,  # +40W during imaging
        downlink_load_w=30.0,  # +30W during ground contact
        adcs_dump_load_w=10.0,  # +10W during momentum dump
        
        # Timing per loads.md
        imaging_duration_min=10.0,  # 10 min imaging per orbit
        downlink_duration_min=8.0,  # 8 min ground pass per orbit
        adcs_dump_duration_min=5.0,  # 5 min ADCS dump per orbit
        downlink_sunlight_fraction=0.5,  # 50% sun, 50% eclipse
        
        # Data budget per loads.md
        data_per_orbit_gbit=2.0,  # 2 Gbit per orbit
        downlink_speed_mbps=50.0,  # 50 Mbps downlink
        max_data_storage_gb=100.0,
        
        # Operational windows (orbit angle ranges)
        imaging_windows_theta=[[20.0, 60.0]],  # ~10 min in sunlight
        ground_pass_window_theta=(95.0, 125.0),  # Spans sun/eclipse boundary
        adcs_dump_window_theta=(65.0, 85.0),  # ~5 min in sunlight
        
        # Simulation
        timestep_min=1.0,
        soc_safety_margin_percent=5.0  # Start protection at 25%
    )


def create_default_state() -> SatelliteState:
    """Create default initial state."""
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
    """Get policy by name."""
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
    Run simulation with loads.md compliance.
    """
    if verbose:
        print("=" * 70)
        print("🛰️  Satellite Digital Twin - loads.md Compliant")
        print("=" * 70)
    
    config = create_loads_md_config()
    initial_state = create_default_state()
    policy = get_policy(policy_name)
    
    if verbose:
        print(f"\n📋 Configuration (per loads.md):")
        print(f"   Orbit: {config.orbit_altitude_km} km SSO, {config.orbit_period_min} min period")
        print(f"   Sunlight: {config.sunlight_duration_min} min / Eclipse: {config.eclipse_duration_min} min")
        print(f"\n⚡ Load Budget:")
        print(f"   Base load: {config.base_load_w}W continuous")
        print(f"   Imaging:   +{config.imaging_load_w}W ({config.imaging_duration_min} min/orbit, sunlight only)")
        print(f"   Downlink:  +{config.downlink_load_w}W ({config.downlink_duration_min} min/orbit)")
        print(f"   ADCS dump: +{config.adcs_dump_load_w}W ({config.adcs_dump_duration_min} min/orbit, sunlight only)")
        print(f"\n💾 Data Budget:")
        print(f"   Generation: {config.data_per_orbit_gbit} Gbit/orbit")
        print(f"   Downlink:   {config.downlink_speed_mbps} Mbps for {config.downlink_duration_min} min")
        print(f"\n🔋 Battery Constraint:")
        print(f"   SoC >= {config.min_soc_percent}% (STRICT)")
        print(f"   Capacity: {config.battery_capacity_wh} Wh")
        print(f"\n📋 Policy: {policy.name}")
        print(f"   Duration: {orbits} orbits ({orbits * config.orbit_period_min:.0f} min)")
    
    # Run simulation
    sim = Simulation(config, initial_state, policy)
    
    if verbose:
        print(f"\n⏳ Running simulation...")
    
    history = sim.run(duration_orbits=orbits)
    
    if verbose:
        print(f"✅ Simulation complete! {len(history)} timesteps.")
    
    # Compliance report
    summary = sim.get_summary()
    compliance = summary.get('compliance', {})
    
    if verbose:
        print(f"\n📊 Results Summary:")
        print(f"   Total Time: {summary['total_time_min']:.1f} min ({summary['total_orbits']} orbits)")
        print(f"   Battery: min={summary['battery']['min']:.1f}%, max={summary['battery']['max']:.1f}%, avg={summary['battery']['avg']:.1f}%")
        print(f"   Load: max={summary['load']['max']:.1f}W, avg={summary['load']['avg']:.1f}W")
        print(f"   Data Generated: {summary['data']['total_generated']:.3f} GB")
        print(f"   Data Downlinked: {summary['data']['total_downlinked']:.3f} GB")
        
        print(f"\n🔋 20% SoC Compliance:")
        print(f"   Minimum SoC reached: {compliance.get('min_soc_reached', 0):.1f}%")
        print(f"   Violations: {compliance.get('soc_violations', 0)}")
        if compliance.get('compliant', False):
            print(f"   Status: ✅ COMPLIANT")
        else:
            print(f"   Status: ❌ NON-COMPLIANT")
    
    # Export results
    if export_path:
        export_dir = Path(export_path)
        export_dir.mkdir(parents=True, exist_ok=True)
        
        exporter = TimeSeriesExporter(history)
        csv_path = exporter.to_csv(export_dir / "simulation_results.csv")
        json_path = exporter.to_json(export_dir / "simulation_results.json")
        
        # Save compliance report
        import json
        compliance_report = sim.get_compliance_report()
        with open(export_dir / "compliance_report.json", 'w') as f:
            json.dump(compliance_report, f, indent=2)
        
        if verbose:
            print(f"\n💾 Results exported to: {export_dir}")
        
        try:
            viz = Visualizer(history)
            viz.save_all_plots(export_dir, prefix="sim")
        except ImportError:
            pass
    
    # Show plots
    if show_plots:
        try:
            viz = Visualizer(history)
            viz.plot_overview(show=True)
        except ImportError:
            if verbose:
                print("\n⚠️ matplotlib not installed for plots")
    
    return sim, history


def show_compliance_info():
    """Show loads.md compliance information."""
    print("=" * 70)
    print("📋 loads.md Compliance Specification")
    print("=" * 70)
    
    print("\n## Load Budget")
    print("-" * 40)
    print("Platform base load:     15W continuous")
    print("Payload imaging:       +40W (sunlight only, 10 min/orbit)")
    print("Downlink (high-rate): +30W (8 min/orbit, 50% sun/50% eclipse)")
    print("ADCS momentum dump:   +10W (sunlight only, 5 min/orbit)")
    
    print("\n## Power Scenarios")
    print("-" * 40)
    print("Base only:              15W")
    print("Base + Imaging:         55W")
    print("Base + Downlink:        45W")
    print("Base + ADCS dump:       25W")
    print("Peak (Imaging + ADCS):  65W")
    
    print("\n## Data Budget")
    print("-" * 40)
    print("Data generation:     2 Gbit per orbit (0.25 GB)")
    print("Imaging duration:    10 minutes per orbit")
    print("Generation rate:     0.025 GB/min during imaging")
    print("Downlink rate:       50 Mbps")
    print("Downlink duration:   8 minutes per orbit")
    print("Downlink capacity:   3 GB per pass")
    
    print("\n## Critical Constraint")
    print("-" * 40)
    print("Battery SoC shall NEVER drop below 20%")
    print("Safety margin: Load shedding at 25%")
    
    print("\n## Energy Analysis (per orbit)")
    print("-" * 40)
    print("Sunlight (60 min @ 60W solar):     60 Wh generated")
    print("Eclipse (35 min @ 15W base):       8.75 Wh consumed")
    print("Imaging (10 min @ 55W):            9.17 Wh consumed")
    print("Downlink (8 min @ 45W):            6.0 Wh consumed")
    print("ADCS dump (5 min @ 25W):           2.08 Wh consumed")
    print("Net per orbit (nominal):          ~+34 Wh (charging)")


def launch_dashboard():
    """Launch the Streamlit dashboard."""
    import subprocess
    dashboard_path = Path(__file__).parent / "output" / "dashboard.py"
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(dashboard_path)])


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Satellite Digital Twin (loads.md compliant)",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('--dashboard', '-d', action='store_true',
                        help='Launch web dashboard')
    parser.add_argument('--orbits', '-o', type=int, default=5,
                        help='Number of orbits (default: 5)')
    parser.add_argument('--policy', '-p', 
                        choices=['compliant', 'basic', 'power_save', 'high_performance'],
                        default='compliant',
                        help='Policy (default: compliant)')
    parser.add_argument('--export', '-e', type=str,
                        help='Export directory')
    parser.add_argument('--no-plots', action='store_true',
                        help='Disable plots')
    parser.add_argument('--quiet', '-q', action='store_true',
                        help='Quiet mode')
    parser.add_argument('--compliance', '-c', action='store_true',
                        help='Show compliance specification')
    
    args = parser.parse_args()
    
    if args.compliance:
        show_compliance_info()
        return
    
    if args.dashboard:
        print("🚀 Launching dashboard...")
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
