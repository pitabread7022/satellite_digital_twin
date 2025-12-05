"""
Streamlit dashboard for the satellite digital twin.
Compliant with loads.md specification.
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
from typing import Optional

from satellite.state import SatelliteState, SatelliteConfig
from simulation.engine import Simulation
from simulation.policy import (
    LoadsMDCompliantPolicy,
    BasicPolicy, 
    PowerSavePolicy, 
    HighPerformancePolicy, 
    CustomizablePolicy
)


def create_dashboard():
    """Create and run the Streamlit dashboard."""
    
    st.set_page_config(
        page_title="Satellite Digital Twin",
        page_icon="🛰️",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Custom CSS
    st.markdown("""
        <style>
        .stMetric {
            background-color: #262730;
            border-radius: 10px;
            padding: 10px;
        }
        .compliance-pass {
            color: #2ecc71;
            font-weight: bold;
        }
        .compliance-fail {
            color: #e74c3c;
            font-weight: bold;
        }
        </style>
    """, unsafe_allow_html=True)
    
    st.title("🛰️ Satellite Digital Twin")
    st.markdown("**500km SSO | loads.md Compliant | 20% SoC Protection**")
    
    # Initialize session state
    if 'simulation' not in st.session_state:
        st.session_state.simulation = None
    if 'history' not in st.session_state:
        st.session_state.history = []
    
    # Sidebar configuration
    with st.sidebar:
        st.header("⚙️ Configuration")
        
        # Orbit Parameters
        with st.expander("🌍 Orbit Parameters", expanded=True):
            orbit_period = st.slider("Orbit Period (min)", 80, 110, 95)
            sunlight_duration = st.slider("Sunlight Duration (min)", 40, 70, 60)
            eclipse_duration = orbit_period - sunlight_duration
            st.info(f"Eclipse Duration: {eclipse_duration} min")
        
        # EPS Configuration
        with st.expander("🔋 EPS Configuration", expanded=True):
            solar_power = st.slider("Solar Panel Power (W)", 40, 100, 60)
            battery_capacity = st.slider("Battery Capacity (Wh)", 50, 200, 100)
            st.warning("⚠️ Min SOC: 20% (STRICT per loads.md)")
        
        # Load Budget (per loads.md)
        with st.expander("⚡ Load Budget (loads.md)", expanded=True):
            st.markdown("**Per loads.md specification:**")
            base_load = st.slider("Base Load (W)", 10, 25, 15)
            imaging_load = st.slider("Imaging Load (+W)", 30, 50, 40)
            downlink_load = st.slider("Downlink Load (+W)", 20, 40, 30)
            adcs_dump_load = st.slider("ADCS Dump Load (+W)", 5, 15, 10)
            
            st.markdown("**Timing per orbit:**")
            imaging_duration = st.slider("Imaging (min)", 5, 15, 10)
            downlink_duration = st.slider("Downlink (min)", 5, 12, 8)
            adcs_dump_duration = st.slider("ADCS Dump (min)", 3, 8, 5)
        
        # Data Budget (per loads.md)
        with st.expander("💾 Data Budget (loads.md)", expanded=False):
            data_per_orbit = st.slider("Data Generation (Gbit/orbit)", 1.0, 4.0, 2.0, 0.5)
            downlink_speed = st.slider("Downlink Speed (Mbps)", 20, 100, 50)
            max_storage = st.slider("Max Storage (GB)", 50, 500, 100)
            
            # Show computed rates
            data_per_orbit_gb = data_per_orbit / 8.0
            downlink_capacity = (downlink_speed / 8.0) * downlink_duration * 60 / 1000
            st.info(f"Data/orbit: {data_per_orbit_gb:.3f} GB\nDownlink capacity: {downlink_capacity:.2f} GB/pass")
        
        # Operational Windows
        with st.expander("📷 Operational Windows", expanded=False):
            st.markdown("**Imaging Window (sunlight only)**")
            img_start = st.slider("Imaging Start (°)", 0, 180, 20)
            img_end = st.slider("Imaging End (°)", 20, 180, 60)
            
            st.markdown("**Ground Pass Window**")
            gs_start = st.slider("Ground Pass Start (°)", 60, 180, 95)
            gs_end = st.slider("Ground Pass End (°)", 90, 200, 125)
            
            st.markdown("**ADCS Dump Window (sunlight only)**")
            adcs_start = st.slider("ADCS Start (°)", 40, 120, 65)
            adcs_end = st.slider("ADCS End (°)", 60, 140, 85)
        
        # Policy Selection
        with st.expander("📋 Policy Selection", expanded=True):
            policy_type = st.selectbox(
                "Operation Policy",
                ["Compliant (loads.md)", "Basic", "Power Save", "High Performance", "Customizable"]
            )
            
            if policy_type == "Customizable":
                custom_min_battery = st.slider("Min Battery for Imaging (%)", 25, 80, 40)
        
        # Simulation Settings
        with st.expander("⏱️ Simulation Settings", expanded=True):
            timestep = st.slider("Timestep (minutes)", 0.5, 5.0, 1.0, 0.5)
            duration_orbits = st.slider("Duration (orbits)", 1, 20, 5)
        
        # Initial State
        with st.expander("📊 Initial State", expanded=False):
            init_battery = st.slider("Initial Battery (%)", 30, 100, 80)
            init_data = st.slider("Initial Data (GB)", 0, 50, 0)
            init_angle = st.slider("Initial Orbit Angle (°)", 0, 359, 0)
    
    # Build configuration from sidebar inputs
    config = SatelliteConfig(
        # Orbit
        orbit_period_min=float(orbit_period),
        sunlight_duration_min=float(sunlight_duration),
        eclipse_duration_min=float(eclipse_duration),
        
        # EPS
        solar_panel_power_w=float(solar_power),
        battery_capacity_wh=float(battery_capacity),
        min_soc_percent=20.0,  # STRICT per loads.md
        max_soc_percent=100.0,
        
        # Load budget per loads.md
        base_load_w=float(base_load),
        imaging_load_w=float(imaging_load),
        downlink_load_w=float(downlink_load),
        adcs_dump_load_w=float(adcs_dump_load),
        
        # Timing per loads.md
        imaging_duration_min=float(imaging_duration),
        downlink_duration_min=float(downlink_duration),
        adcs_dump_duration_min=float(adcs_dump_duration),
        
        # Data budget per loads.md
        data_per_orbit_gbit=float(data_per_orbit),
        downlink_speed_mbps=float(downlink_speed),
        max_data_storage_gb=float(max_storage),
        
        # Operational windows
        imaging_windows_theta=[[float(img_start), float(img_end)]],
        ground_pass_window_theta=(float(gs_start), float(gs_end)),
        adcs_dump_window_theta=(float(adcs_start), float(adcs_end)),
        
        # Simulation
        timestep_min=float(timestep)
    )
    
    # Select policy
    if policy_type == "Compliant (loads.md)":
        policy = LoadsMDCompliantPolicy()
    elif policy_type == "Basic":
        policy = BasicPolicy()
    elif policy_type == "Power Save":
        policy = PowerSavePolicy()
    elif policy_type == "High Performance":
        policy = HighPerformancePolicy()
    else:
        policy = CustomizablePolicy(min_battery_imaging=custom_min_battery)
    
    # Initial state
    initial_state = SatelliteState(
        battery_level_percent=float(init_battery),
        battery_energy_wh=float(init_battery) * float(battery_capacity) / 100.0,
        onboard_data_volume_gb=float(init_data),
        orbit_angle_deg=float(init_angle),
        base_load_w=float(base_load),
        total_load_w=float(base_load)
    )
    
    # Main content area
    col1, col2, col3 = st.columns([1, 1, 1])
    
    with col1:
        run_button = st.button("▶️ Run Simulation", type="primary", use_container_width=True)
    with col2:
        if st.session_state.simulation:
            downlink_button = st.button("📡 Trigger Downlink", use_container_width=True)
        else:
            downlink_button = False
    with col3:
        reset_button = st.button("🔄 Reset", use_container_width=True)
    
    if reset_button:
        st.session_state.simulation = None
        st.session_state.history = []
        st.rerun()
    
    if run_button:
        with st.spinner("Running simulation..."):
            sim = Simulation(config, initial_state, policy)
            history = sim.run(duration_orbits=duration_orbits)
            st.session_state.simulation = sim
            st.session_state.history = history
        st.success(f"✅ Simulation complete! {len(history)} timesteps.")
    
    # Display results
    if st.session_state.history:
        history = st.session_state.history
        sim = st.session_state.simulation
        summary = sim.get_summary()
        compliance = summary.get('compliance', {})
        
        # Compliance banner
        st.markdown("---")
        if compliance.get('compliant', False):
            st.success("✅ **20% SoC COMPLIANT** - Battery never dropped below minimum")
        else:
            st.error(f"❌ **SoC VIOLATION** - Battery dropped to {compliance.get('min_soc_reached', 0):.1f}%")
        
        # Final state metrics
        st.subheader("📊 Final State")
        final_state = history[-1]
        
        col1, col2, col3, col4, col5, col6 = st.columns(6)
        
        with col1:
            delta = final_state['battery_level_percent'] - history[0]['battery_level_percent']
            st.metric("🔋 Battery", f"{final_state['battery_level_percent']:.1f}%",
                     delta=f"{delta:+.1f}%")
        
        with col2:
            st.metric("📉 Min SOC", f"{compliance.get('min_soc_reached', 0):.1f}%")
        
        with col3:
            sun_status = "☀️ Sun" if final_state['in_sunlight'] else "🌑 Eclipse"
            st.metric("🌍 Status", sun_status)
        
        with col4:
            st.metric("⚡ Load", f"{final_state['total_load_w']:.0f}W")
        
        with col5:
            st.metric("💾 Data", f"{final_state['onboard_data_volume_gb']:.3f}GB")
        
        with col6:
            st.metric("🛰️ Orbit", f"#{final_state['orbit_number']}")
        
        # Status indicators
        st.markdown("---")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            if final_state.get('in_imaging_window', False):
                st.success("📷 Imaging Window")
            else:
                st.info("📷 Outside Window")
        
        with col2:
            if final_state.get('in_ground_pass_window', False):
                st.success("📡 Ground Pass")
            else:
                st.info("📡 No Contact")
        
        with col3:
            if final_state.get('is_imaging', False):
                st.success("🔴 Imaging Active")
            else:
                st.info("⚪ Imaging Idle")
        
        with col4:
            if final_state.get('is_downlinking', False):
                st.success("📡 Downlinking")
            else:
                st.info("📡 Downlink Idle")
        
        # Plots
        st.markdown("---")
        st.subheader("📈 Simulation Results")
        
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "Overview", "Battery", "Power Budget", "Data", "Compliance"
        ])
        
        df = pd.DataFrame(history)
        df['time_min'] = df['simulation_time_s'] / 60.0
        
        with tab1:
            fig = make_subplots(
                rows=3, cols=1,
                shared_xaxes=True,
                vertical_spacing=0.08,
                subplot_titles=('Battery SOC (%)', 'Power (W)', 'Data Volume (GB)')
            )
            
            # Battery
            fig.add_trace(
                go.Scatter(x=df['time_min'], y=df['battery_level_percent'],
                          mode='lines', name='Battery SOC',
                          line=dict(color='#2ecc71', width=2)),
                row=1, col=1
            )
            fig.add_hline(y=20, line_dash="dash", line_color="red", 
                         annotation_text="20% Min", row=1, col=1)
            
            # Power
            fig.add_trace(
                go.Scatter(x=df['time_min'], y=df['solar_generation_w'],
                          mode='lines', name='Solar',
                          line=dict(color='#f1c40f', width=2)),
                row=2, col=1
            )
            fig.add_trace(
                go.Scatter(x=df['time_min'], y=df['total_load_w'],
                          mode='lines', name='Load',
                          line=dict(color='#e74c3c', width=2)),
                row=2, col=1
            )
            
            # Data
            fig.add_trace(
                go.Scatter(x=df['time_min'], y=df['onboard_data_volume_gb'],
                          mode='lines', name='Data',
                          fill='tozeroy',
                          line=dict(color='#3498db', width=2)),
                row=3, col=1
            )
            
            _add_eclipse_regions(fig, df)
            
            fig.update_layout(height=700, showlegend=True)
            fig.update_yaxes(title_text="SOC (%)", row=1, col=1, range=[0, 100])
            fig.update_yaxes(title_text="Power (W)", row=2, col=1)
            fig.update_yaxes(title_text="Data (GB)", row=3, col=1)
            fig.update_xaxes(title_text="Time (minutes)", row=3, col=1)
            
            st.plotly_chart(fig, use_container_width=True)
        
        with tab2:
            fig = make_subplots(
                rows=2, cols=2,
                specs=[[{"type": "scatter"}, {"type": "indicator"}],
                       [{"type": "scatter"}, {"type": "scatter"}]],
                subplot_titles=('SOC Over Time', 'Current SOC',
                              'Battery Voltage', 'Net Power')
            )
            
            fig.add_trace(
                go.Scatter(x=df['time_min'], y=df['battery_level_percent'],
                          mode='lines', line=dict(color='#2ecc71', width=2)),
                row=1, col=1
            )
            
            fig.add_trace(
                go.Indicator(
                    mode="gauge+number+delta",
                    value=final_state['battery_level_percent'],
                    delta={'reference': history[0]['battery_level_percent']},
                    gauge={
                        'axis': {'range': [0, 100]},
                        'bar': {'color': '#2ecc71'},
                        'steps': [
                            {'range': [0, 20], 'color': "#ff6b6b"},
                            {'range': [20, 25], 'color': "#ffd93d"},
                            {'range': [25, 100], 'color': "#e8e8e8"}
                        ],
                        'threshold': {
                            'line': {'color': "red", 'width': 4},
                            'thickness': 0.75,
                            'value': 20
                        }
                    }
                ),
                row=1, col=2
            )
            
            fig.add_trace(
                go.Scatter(x=df['time_min'], y=df['battery_voltage_v'],
                          mode='lines', line=dict(color='#8e44ad', width=2)),
                row=2, col=1
            )
            
            fig.add_trace(
                go.Scatter(x=df['time_min'], y=df['net_power_w'],
                          mode='lines', fill='tozeroy',
                          line=dict(color='#3498db', width=2)),
                row=2, col=2
            )
            
            fig.update_layout(height=600, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
        
        with tab3:
            fig = go.Figure()
            
            # Stack loads per loads.md categories
            fig.add_trace(go.Scatter(
                x=df['time_min'], y=df['base_load_w'],
                mode='lines', name=f'Base ({base_load}W)',
                stackgroup='loads',
                line=dict(color='#3498db')
            ))
            fig.add_trace(go.Scatter(
                x=df['time_min'], y=df['payload_load_w'],
                mode='lines', name=f'Imaging (+{imaging_load}W)',
                stackgroup='loads',
                line=dict(color='#9b59b6')
            ))
            fig.add_trace(go.Scatter(
                x=df['time_min'], y=df['comms_load_w'],
                mode='lines', name=f'Downlink (+{downlink_load}W)',
                stackgroup='loads',
                line=dict(color='#2ecc71')
            ))
            if 'adcs_dump_load_w' in df.columns:
                fig.add_trace(go.Scatter(
                    x=df['time_min'], y=df['adcs_dump_load_w'],
                    mode='lines', name=f'ADCS Dump (+{adcs_dump_load}W)',
                    stackgroup='loads',
                    line=dict(color='#e67e22')
                ))
            
            fig.add_trace(go.Scatter(
                x=df['time_min'], y=df['solar_generation_w'],
                mode='lines', name='Solar Generation',
                line=dict(color='#f1c40f', width=3, dash='dash')
            ))
            
            fig.update_layout(
                title='Power Budget (per loads.md)',
                xaxis_title='Time (minutes)',
                yaxis_title='Power (W)',
                height=500
            )
            
            st.plotly_chart(fig, use_container_width=True)
            
            # Load budget summary
            st.markdown("**loads.md Power Scenarios:**")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.write(f"Base only: {base_load}W")
                st.write(f"+ Imaging: {base_load + imaging_load}W")
            with col2:
                st.write(f"+ Downlink: {base_load + downlink_load}W")
                st.write(f"+ ADCS dump: {base_load + adcs_dump_load}W")
            with col3:
                st.write(f"Peak: {base_load + imaging_load + adcs_dump_load}W")
        
        with tab4:
            col1, col2 = st.columns(2)
            
            with col1:
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=df['time_min'], y=df['onboard_data_volume_gb'],
                    mode='lines', fill='tozeroy',
                    line=dict(color='#3498db', width=2)
                ))
                fig.add_hline(y=max_storage, line_dash="dash", line_color="red")
                fig.update_layout(
                    title='Onboard Data Volume',
                    xaxis_title='Time (minutes)',
                    yaxis_title='Data (GB)',
                    height=400
                )
                st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                st.markdown("**📊 Data Budget (loads.md)**")
                data_stats = summary.get('data', {})
                st.metric("Generated", f"{data_stats.get('total_generated', 0):.3f} GB")
                st.metric("Downlinked", f"{data_stats.get('total_downlinked', 0):.3f} GB")
                st.metric("Remaining", f"{data_stats.get('final_stored', 0):.3f} GB")
                
                st.markdown("**Spec:**")
                st.write(f"- {data_per_orbit} Gbit/orbit")
                st.write(f"- {downlink_speed} Mbps downlink")
        
        with tab5:
            st.subheader("🔋 20% SoC Compliance Report")
            
            report = sim.get_compliance_report()
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("**Battery Status**")
                soc_comp = report.get('soc_compliance', {})
                st.write(f"- Requirement: {soc_comp.get('requirement', 'N/A')}")
                st.write(f"- Minimum Reached: {soc_comp.get('min_soc_reached', 0):.1f}%")
                st.write(f"- Violations: {soc_comp.get('violations', 0)}")
                
                if soc_comp.get('compliant', False):
                    st.success("✅ COMPLIANT")
                else:
                    st.error("❌ NON-COMPLIANT")
            
            with col2:
                st.markdown("**Load Profile (loads.md)**")
                load_prof = report.get('load_profile', {})
                st.write(f"- Base: {load_prof.get('base_load_w', 0)}W")
                st.write(f"- Imaging: +{load_prof.get('imaging_load_w', 0)}W")
                st.write(f"- Downlink: +{load_prof.get('downlink_load_w', 0)}W")
                st.write(f"- ADCS Dump: +{load_prof.get('adcs_dump_load_w', 0)}W")
            
            st.markdown("---")
            st.markdown("**Timing Budget (per orbit)**")
            timing = report.get('timing_budget', {})
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Imaging", f"{timing.get('imaging_per_orbit_min', 0)} min")
            with col2:
                st.metric("Downlink", f"{timing.get('downlink_per_orbit_min', 0)} min")
            with col3:
                st.metric("ADCS Dump", f"{timing.get('adcs_dump_per_orbit_min', 0)} min")
        
        # Events log
        st.markdown("---")
        st.subheader("📋 Events Log")
        
        events = sim.get_events()
        if events:
            events_df = pd.DataFrame([
                {
                    'Time': f"{e.time_s/60:.1f} min",
                    'SOC': f"{e.battery_soc:.1f}%",
                    'Type': e.event_type,
                    'Description': e.description
                }
                for e in events[-30:]
            ])
            st.dataframe(events_df, use_container_width=True)
        
        # Export
        st.markdown("---")
        st.subheader("💾 Export")
        
        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                "📥 Download CSV",
                df.to_csv(index=False),
                "simulation_results.csv",
                "text/csv",
                use_container_width=True
            )
        with col2:
            import json
            st.download_button(
                "📥 Download JSON",
                json.dumps(history, indent=2, default=str),
                "simulation_results.json",
                "application/json",
                use_container_width=True
            )
    
    else:
        # No simulation yet
        st.info("👆 Configure parameters and click **Run Simulation**")
        
        st.markdown("---")
        st.subheader("📋 loads.md Specification")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown("**⚡ Load Budget**")
            st.write(f"- Base: {base_load}W continuous")
            st.write(f"- Imaging: +{imaging_load}W")
            st.write(f"- Downlink: +{downlink_load}W")
            st.write(f"- ADCS dump: +{adcs_dump_load}W")
        
        with col2:
            st.markdown("**⏱️ Timing/Orbit**")
            st.write(f"- Imaging: {imaging_duration} min")
            st.write(f"- Downlink: {downlink_duration} min")
            st.write(f"- ADCS dump: {adcs_dump_duration} min")
        
        with col3:
            st.markdown("**🔋 Constraint**")
            st.write("- **SoC >= 20%** (STRICT)")
            st.write(f"- Battery: {battery_capacity} Wh")
            st.write(f"- Solar: {solar_power} W")


def _add_eclipse_regions(fig, df):
    """Add eclipse shading to plotly figure."""
    shapes = []
    in_eclipse = False
    eclipse_start = 0
    
    for i, row in df.iterrows():
        if not row['in_sunlight'] and not in_eclipse:
            eclipse_start = row['time_min']
            in_eclipse = True
        elif row['in_sunlight'] and in_eclipse:
            shapes.append(dict(
                type="rect", xref="x", yref="paper",
                x0=eclipse_start, x1=row['time_min'],
                y0=0, y1=1,
                fillcolor="gray", opacity=0.15,
                layer="below", line_width=0
            ))
            in_eclipse = False
    
    if in_eclipse:
        shapes.append(dict(
            type="rect", xref="x", yref="paper",
            x0=eclipse_start, x1=df['time_min'].iloc[-1],
            y0=0, y1=1,
            fillcolor="gray", opacity=0.15,
            layer="below", line_width=0
        ))
    
    fig.update_layout(shapes=shapes)


def run_dashboard():
    """Entry point to run the dashboard."""
    create_dashboard()


if __name__ == "__main__":
    run_dashboard()
