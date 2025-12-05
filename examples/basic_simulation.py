#!/usr/bin/env python3
"""
Basic simulation example demonstrating the satellite digital twin.

This example shows:
1. Creating a custom configuration
2. Setting initial state
3. Running a simulation with a policy
4. Analyzing results
5. Exporting data
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from satellite.state import SatelliteState, SatelliteConfig
from simulation.engine import Simulation
from simulation.policy import BasicPolicy, CustomizablePolicy
from output.timeseries import TimeSeriesExporter
from output.visualization import Visualizer


def example_basic_simulation():
    """Run a basic simulation with default parameters."""
    print("=== Basic Simulation Example ===\n")
    
    # Use default configuration (matches requirements)
    config = SatelliteConfig(
        # Orbit parameters
        orbit_period_min=95.0,
        sunlight_duration_min=60.0,
        eclipse_duration_min=35.0,
        
        # EPS
        solar_panel_power_w=60.0,
        battery_capacity_wh=100.0,
        min_soc_percent=20.0,
        max_soc_percent=80.0,
        
        # Imaging windows
        imaging_windows_theta=[[23.0, 28.0], [45.0, 50.0]],
        
        # Simulation timestep
        timestep_min=1.0
    )
    
    # Initial state
    initial_state = SatelliteState(
        battery_level_percent=82.0,
        battery_voltage_v=12.5,
        battery_energy_wh=82.0,
        total_load_w=23.0,
        onboard_data_volume_gb=0.0,
        temperature_c=287.0,
        battery_health_percent=97.0
    )
    
    # Create simulation with BasicPolicy
    policy = BasicPolicy()
    sim = Simulation(config, initial_state, policy)
    
    # Run for 5 orbits
    print("Running simulation for 5 orbits...")
    history = sim.run(duration_orbits=5)
    
    # Print summary
    summary = sim.get_summary()
    print(f"\nSimulation Complete!")
    print(f"  Total Time: {summary['total_time_min']:.1f} minutes")
    print(f"  Orbits: {summary['total_orbits']}")
    print(f"  Battery Range: {summary['battery']['min']:.1f}% - {summary['battery']['max']:.1f}%")
    print(f"  Data Generated: {summary['data']['total_generated']:.2f} GB")
    print(f"  Events: {summary['events_count']}")
    
    return sim, history


def example_custom_policy():
    """Example with a custom policy configuration."""
    print("\n=== Custom Policy Example ===\n")
    
    config = SatelliteConfig()
    
    # Create customizable policy with specific thresholds
    policy = CustomizablePolicy(
        name="ConservativePolicy",
        min_battery_imaging=50.0,  # Only image when battery > 50%
        min_battery_downlink=40.0,  # Only downlink when battery > 40%
        storage_downlink_trigger=50.0,  # Start downlink at 50% storage
        eclipse_load_reduction=0.4,  # Reduce load by 60% during eclipse
        safe_mode_threshold=30.0,  # Enter safe mode below 30% battery
        enable_opportunistic_imaging=False  # Strict imaging window adherence
    )
    
    sim = Simulation(config, policy=policy)
    history = sim.run(duration_orbits=3)
    
    print("Policy Parameters:")
    for key, value in policy.get_parameters().items():
        print(f"  {key}: {value}")
    
    summary = sim.get_summary()
    print(f"\nResults with conservative policy:")
    print(f"  Battery Range: {summary['battery']['min']:.1f}% - {summary['battery']['max']:.1f}%")
    
    return sim, history


def example_data_export():
    """Example of exporting simulation results."""
    print("\n=== Data Export Example ===\n")
    
    # Run a quick simulation
    sim = Simulation()
    history = sim.run(duration_orbits=2)
    
    # Create exporter
    exporter = TimeSeriesExporter(history)
    
    # Export to CSV (specific columns)
    csv_path = exporter.to_csv(
        "example_results.csv",
        columns=['simulation_time_s', 'battery_level_percent', 'solar_generation_w', 'total_load_w']
    )
    print(f"Exported CSV: {csv_path}")
    
    # Export to JSON (all data)
    json_path = exporter.to_json("example_results.json")
    print(f"Exported JSON: {json_path}")
    
    # Get statistics
    battery_stats = exporter.get_column_stats('battery_level_percent')
    print(f"\nBattery Statistics:")
    for key, value in battery_stats.items():
        print(f"  {key}: {value:.2f}")
    
    # Resample for lower resolution
    resampled = exporter.resample(factor=5, method='mean')
    print(f"\nOriginal records: {len(exporter.history)}")
    print(f"Resampled records: {len(resampled.history)}")


def example_manual_control():
    """Example of manual simulation control."""
    print("\n=== Manual Control Example ===\n")
    
    sim = Simulation()
    
    # Step through manually
    print("Stepping through simulation manually...")
    
    for i in range(10):
        state = sim.step()
        
        # Manually trigger downlink when data exceeds 5 GB
        if state.onboard_data_volume_gb > 5.0 and not state.is_downlinking:
            print(f"  Step {i}: Data={state.onboard_data_volume_gb:.2f}GB - Triggering downlink!")
            sim.trigger_downlink()
        
        # Stop downlink when data below 1 GB
        if state.onboard_data_volume_gb < 1.0 and state.is_downlinking:
            print(f"  Step {i}: Data={state.onboard_data_volume_gb:.2f}GB - Stopping downlink")
            sim.stop_downlink()
    
    print(f"\nFinal state: {sim.get_state().get_summary()}")


def example_visualization():
    """Example of creating visualizations."""
    print("\n=== Visualization Example ===\n")
    
    # Run simulation
    sim = Simulation()
    history = sim.run(duration_orbits=3)
    
    # Create visualizer
    viz = Visualizer(history)
    
    try:
        # Save plots (without displaying)
        print("Generating plots...")
        viz.plot_overview(save_path="example_overview.png", show=False)
        viz.plot_battery_detail(save_path="example_battery.png", show=False)
        viz.plot_power_breakdown(save_path="example_power.png", show=False)
        print("Saved: example_overview.png, example_battery.png, example_power.png")
        
        # Interactive plot (Plotly)
        fig = viz.plot_interactive_overview()
        fig.write_html("example_interactive.html")
        print("Saved: example_interactive.html")
        
    except ImportError as e:
        print(f"Visualization libraries not installed: {e}")
        print("Install with: pip install matplotlib plotly")


def example_callback():
    """Example of using step callbacks for custom logging."""
    print("\n=== Callback Example ===\n")
    
    eclipse_entries = []
    
    def on_eclipse_entry(state: SatelliteState):
        """Callback to log eclipse entries."""
        if not state.in_sunlight:
            eclipse_entries.append({
                'time_min': state.simulation_time_s / 60.0,
                'battery': state.battery_level_percent
            })
    
    sim = Simulation()
    sim.add_step_callback(on_eclipse_entry)
    
    # Run simulation
    history = sim.run(duration_orbits=2)
    
    print(f"Eclipse entries detected: {len(eclipse_entries)}")
    for entry in eclipse_entries[:5]:  # Show first 5
        print(f"  Time: {entry['time_min']:.1f} min, Battery: {entry['battery']:.1f}%")


if __name__ == "__main__":
    # Run all examples
    example_basic_simulation()
    example_custom_policy()
    example_data_export()
    example_manual_control()
    
    # These require matplotlib/plotly
    try:
        example_visualization()
    except ImportError:
        print("\n(Skipping visualization example - matplotlib/plotly not installed)")
    
    example_callback()
    
    print("\n" + "=" * 50)
    print("All examples completed!")
    print("=" * 50)





