"""
Visualization module for simulation results.
Supports both matplotlib (static) and plotly (interactive) plots.
"""

from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path


class Visualizer:
    """
    Create visualizations of simulation history.
    
    Supports:
    - Matplotlib static plots (for reports, saving to files)
    - Plotly interactive plots (for exploration, dashboards)
    """
    
    # Color scheme
    COLORS = {
        'battery': '#2ecc71',      # Green
        'solar': '#f1c40f',        # Yellow
        'load': '#e74c3c',         # Red
        'data': '#3498db',         # Blue
        'eclipse': '#95a5a6',      # Gray
        'imaging': '#9b59b6',      # Purple
        'warning': '#e67e22'       # Orange
    }
    
    def __init__(self, history: List[Dict[str, Any]]):
        """
        Initialize visualizer with simulation history.
        
        Args:
            history: List of state dictionaries from simulation
        """
        self.history = history
        self._extract_timeseries()
    
    def _extract_timeseries(self) -> None:
        """Extract common time series from history."""
        if not self.history:
            self.time_min = []
            return
        
        self.time_min = [h['simulation_time_s'] / 60.0 for h in self.history]
        self.time_hours = [t / 60.0 for t in self.time_min]
        self.orbits = [h['orbit_number'] for h in self.history]
        self.orbit_angles = [h['orbit_angle_deg'] for h in self.history]
        
        # EPS data
        self.battery_percent = [h['battery_level_percent'] for h in self.history]
        self.battery_voltage = [h['battery_voltage_v'] for h in self.history]
        self.solar_gen = [h['solar_generation_w'] for h in self.history]
        self.total_load = [h['total_load_w'] for h in self.history]
        self.net_power = [h['net_power_w'] for h in self.history]
        
        # Data system
        self.data_volume = [h['onboard_data_volume_gb'] for h in self.history]
        
        # Flags
        self.in_sunlight = [h['in_sunlight'] for h in self.history]
        self.in_imaging = [h.get('is_imaging', False) for h in self.history]
        self.in_downlink = [h.get('is_downlinking', False) for h in self.history]
    
    # ==================== MATPLOTLIB PLOTS ====================
    
    def plot_overview(self, 
                      figsize: Tuple[int, int] = (14, 10),
                      save_path: Optional[str] = None,
                      show: bool = True):
        """
        Create overview plot with all key metrics.
        
        Args:
            figsize: Figure size in inches
            save_path: Path to save figure (optional)
            show: Whether to display the plot
        """
        try:
            import matplotlib.pyplot as plt
            import matplotlib.patches as mpatches
        except ImportError:
            raise ImportError("matplotlib is required. Install with: pip install matplotlib")
        
        fig, axes = plt.subplots(4, 1, figsize=figsize, sharex=True)
        fig.suptitle('Satellite Digital Twin - Simulation Overview', fontsize=14, fontweight='bold')
        
        # Plot 1: Battery State of Charge
        ax1 = axes[0]
        ax1.plot(self.time_min, self.battery_percent, color=self.COLORS['battery'], 
                 linewidth=2, label='Battery SOC')
        ax1.axhline(y=20, color='r', linestyle='--', alpha=0.5, label='Min SOC (20%)')
        ax1.axhline(y=80, color='orange', linestyle='--', alpha=0.5, label='Max SOC (80%)')
        ax1.set_ylabel('Battery SOC (%)')
        ax1.set_ylim(0, 100)
        ax1.legend(loc='upper right')
        ax1.grid(True, alpha=0.3)
        self._add_eclipse_shading(ax1)
        
        # Plot 2: Power Balance
        ax2 = axes[1]
        ax2.plot(self.time_min, self.solar_gen, color=self.COLORS['solar'], 
                 linewidth=2, label='Solar Generation')
        ax2.plot(self.time_min, self.total_load, color=self.COLORS['load'], 
                 linewidth=2, label='Total Load')
        ax2.fill_between(self.time_min, self.net_power, 0, 
                        where=[n >= 0 for n in self.net_power],
                        color=self.COLORS['battery'], alpha=0.3, label='Charging')
        ax2.fill_between(self.time_min, self.net_power, 0,
                        where=[n < 0 for n in self.net_power],
                        color=self.COLORS['load'], alpha=0.3, label='Discharging')
        ax2.set_ylabel('Power (W)')
        ax2.legend(loc='upper right')
        ax2.grid(True, alpha=0.3)
        self._add_eclipse_shading(ax2)
        
        # Plot 3: Data Volume
        ax3 = axes[2]
        ax3.plot(self.time_min, self.data_volume, color=self.COLORS['data'], 
                 linewidth=2, label='Onboard Data')
        ax3.set_ylabel('Data Volume (GB)')
        ax3.legend(loc='upper right')
        ax3.grid(True, alpha=0.3)
        self._add_eclipse_shading(ax3)
        self._add_imaging_markers(ax3)
        
        # Plot 4: Orbit Position
        ax4 = axes[3]
        ax4.plot(self.time_min, self.orbit_angles, color='#34495e', 
                 linewidth=1, label='Orbit Angle')
        ax4.set_ylabel('Orbit Angle (°)')
        ax4.set_xlabel('Time (minutes)')
        ax4.set_ylim(0, 360)
        ax4.legend(loc='upper right')
        ax4.grid(True, alpha=0.3)
        self._add_eclipse_shading(ax4)
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight')
        
        if show:
            plt.show()
        
        return fig
    
    def plot_battery_detail(self,
                           figsize: Tuple[int, int] = (12, 8),
                           save_path: Optional[str] = None,
                           show: bool = True):
        """Create detailed battery analysis plot."""
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            raise ImportError("matplotlib is required")
        
        fig, axes = plt.subplots(3, 1, figsize=figsize, sharex=True)
        fig.suptitle('Battery Analysis', fontsize=14, fontweight='bold')
        
        # SOC
        ax1 = axes[0]
        ax1.plot(self.time_min, self.battery_percent, color=self.COLORS['battery'], linewidth=2)
        ax1.axhline(y=20, color='r', linestyle='--', alpha=0.5)
        ax1.axhline(y=80, color='orange', linestyle='--', alpha=0.5)
        ax1.set_ylabel('SOC (%)')
        ax1.set_ylim(0, 100)
        ax1.grid(True, alpha=0.3)
        self._add_eclipse_shading(ax1)
        
        # Voltage
        ax2 = axes[1]
        ax2.plot(self.time_min, self.battery_voltage, color='#8e44ad', linewidth=2)
        ax2.set_ylabel('Voltage (V)')
        ax2.grid(True, alpha=0.3)
        self._add_eclipse_shading(ax2)
        
        # Net Power
        ax3 = axes[2]
        ax3.fill_between(self.time_min, self.net_power, 0,
                        where=[n >= 0 for n in self.net_power],
                        color=self.COLORS['battery'], alpha=0.7, label='Charging')
        ax3.fill_between(self.time_min, self.net_power, 0,
                        where=[n < 0 for n in self.net_power],
                        color=self.COLORS['load'], alpha=0.7, label='Discharging')
        ax3.axhline(y=0, color='k', linewidth=0.5)
        ax3.set_ylabel('Net Power (W)')
        ax3.set_xlabel('Time (minutes)')
        ax3.legend(loc='upper right')
        ax3.grid(True, alpha=0.3)
        self._add_eclipse_shading(ax3)
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight')
        if show:
            plt.show()
        
        return fig
    
    def plot_power_breakdown(self,
                            figsize: Tuple[int, int] = (12, 6),
                            save_path: Optional[str] = None,
                            show: bool = True):
        """Create power breakdown stacked area plot."""
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            raise ImportError("matplotlib is required")
        
        # Extract load breakdown
        base_load = [h.get('base_load_w', 0) for h in self.history]
        payload_load = [h.get('payload_load_w', 0) for h in self.history]
        heater_load = [h.get('heater_load_w', 0) for h in self.history]
        comms_load = [h.get('comms_load_w', 0) for h in self.history]
        
        fig, ax = plt.subplots(figsize=figsize)
        
        ax.stackplot(self.time_min, 
                    base_load, payload_load, heater_load, comms_load,
                    labels=['Base', 'Payload', 'Heater', 'Comms'],
                    colors=['#3498db', '#9b59b6', '#e74c3c', '#2ecc71'],
                    alpha=0.8)
        
        ax.plot(self.time_min, self.solar_gen, 'k--', linewidth=2, 
                label='Solar Generation')
        
        ax.set_xlabel('Time (minutes)')
        ax.set_ylabel('Power (W)')
        ax.set_title('Power Budget Breakdown')
        ax.legend(loc='upper right')
        ax.grid(True, alpha=0.3)
        self._add_eclipse_shading(ax)
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight')
        if show:
            plt.show()
        
        return fig
    
    def _add_eclipse_shading(self, ax) -> None:
        """Add gray shading for eclipse periods."""
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            return
        
        in_eclipse = False
        eclipse_start = 0
        
        for i, sunlight in enumerate(self.in_sunlight):
            if not sunlight and not in_eclipse:
                eclipse_start = self.time_min[i]
                in_eclipse = True
            elif sunlight and in_eclipse:
                ax.axvspan(eclipse_start, self.time_min[i], 
                          alpha=0.2, color=self.COLORS['eclipse'])
                in_eclipse = False
        
        # Handle case where simulation ends in eclipse
        if in_eclipse:
            ax.axvspan(eclipse_start, self.time_min[-1],
                      alpha=0.2, color=self.COLORS['eclipse'])
    
    def _add_imaging_markers(self, ax) -> None:
        """Add markers for imaging periods."""
        imaging_times = [t for t, img in zip(self.time_min, self.in_imaging) if img]
        if imaging_times:
            ax.scatter(imaging_times, [0] * len(imaging_times),
                      color=self.COLORS['imaging'], marker='|', s=100, alpha=0.5,
                      label='Imaging')
    
    # ==================== PLOTLY PLOTS ====================
    
    def plot_interactive_overview(self):
        """
        Create interactive plotly overview figure.
        
        Returns:
            plotly Figure object
        """
        try:
            import plotly.graph_objects as go
            from plotly.subplots import make_subplots
        except ImportError:
            raise ImportError("plotly is required. Install with: pip install plotly")
        
        fig = make_subplots(
            rows=4, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.05,
            subplot_titles=(
                'Battery State of Charge',
                'Power Balance',
                'Data Volume',
                'Orbit Position'
            )
        )
        
        # Battery SOC
        fig.add_trace(
            go.Scatter(x=self.time_min, y=self.battery_percent,
                      mode='lines', name='Battery SOC',
                      line=dict(color=self.COLORS['battery'], width=2)),
            row=1, col=1
        )
        fig.add_hline(y=20, line_dash="dash", line_color="red", 
                     annotation_text="Min SOC", row=1, col=1)
        fig.add_hline(y=80, line_dash="dash", line_color="orange",
                     annotation_text="Max SOC", row=1, col=1)
        
        # Power
        fig.add_trace(
            go.Scatter(x=self.time_min, y=self.solar_gen,
                      mode='lines', name='Solar Generation',
                      line=dict(color=self.COLORS['solar'], width=2)),
            row=2, col=1
        )
        fig.add_trace(
            go.Scatter(x=self.time_min, y=self.total_load,
                      mode='lines', name='Total Load',
                      line=dict(color=self.COLORS['load'], width=2)),
            row=2, col=1
        )
        
        # Data Volume
        fig.add_trace(
            go.Scatter(x=self.time_min, y=self.data_volume,
                      mode='lines', name='Onboard Data',
                      fill='tozeroy',
                      line=dict(color=self.COLORS['data'], width=2)),
            row=3, col=1
        )
        
        # Orbit Angle
        fig.add_trace(
            go.Scatter(x=self.time_min, y=self.orbit_angles,
                      mode='lines', name='Orbit Angle',
                      line=dict(color='#34495e', width=1)),
            row=4, col=1
        )
        
        # Add eclipse shading
        self._add_plotly_eclipse_shapes(fig)
        
        # Update layout
        fig.update_layout(
            height=800,
            title_text="Satellite Digital Twin - Interactive Overview",
            showlegend=True
        )
        
        fig.update_yaxes(title_text="SOC (%)", row=1, col=1, range=[0, 100])
        fig.update_yaxes(title_text="Power (W)", row=2, col=1)
        fig.update_yaxes(title_text="Data (GB)", row=3, col=1)
        fig.update_yaxes(title_text="Angle (°)", row=4, col=1, range=[0, 360])
        fig.update_xaxes(title_text="Time (minutes)", row=4, col=1)
        
        return fig
    
    def plot_interactive_battery(self):
        """Create interactive battery analysis figure."""
        try:
            import plotly.graph_objects as go
            from plotly.subplots import make_subplots
        except ImportError:
            raise ImportError("plotly is required")
        
        fig = make_subplots(
            rows=2, cols=2,
            specs=[[{"type": "scatter"}, {"type": "indicator"}],
                   [{"type": "scatter"}, {"type": "scatter"}]],
            subplot_titles=('Battery SOC Over Time', 'Current SOC',
                          'Battery Voltage', 'Net Power')
        )
        
        # SOC timeline
        fig.add_trace(
            go.Scatter(x=self.time_min, y=self.battery_percent,
                      mode='lines', name='SOC',
                      line=dict(color=self.COLORS['battery'], width=2)),
            row=1, col=1
        )
        
        # Current SOC gauge
        current_soc = self.battery_percent[-1] if self.battery_percent else 0
        fig.add_trace(
            go.Indicator(
                mode="gauge+number",
                value=current_soc,
                title={'text': "SOC (%)"},
                gauge={
                    'axis': {'range': [0, 100]},
                    'bar': {'color': self.COLORS['battery']},
                    'steps': [
                        {'range': [0, 20], 'color': "red"},
                        {'range': [20, 80], 'color': "lightgray"},
                        {'range': [80, 100], 'color': "orange"}
                    ],
                    'threshold': {
                        'line': {'color': "black", 'width': 2},
                        'value': current_soc
                    }
                }
            ),
            row=1, col=2
        )
        
        # Voltage
        fig.add_trace(
            go.Scatter(x=self.time_min, y=self.battery_voltage,
                      mode='lines', name='Voltage',
                      line=dict(color='#8e44ad', width=2)),
            row=2, col=1
        )
        
        # Net Power
        fig.add_trace(
            go.Scatter(x=self.time_min, y=self.net_power,
                      mode='lines', name='Net Power',
                      fill='tozeroy',
                      line=dict(color='#3498db', width=2)),
            row=2, col=2
        )
        
        fig.update_layout(height=600, title_text="Battery Analysis")
        
        return fig
    
    def _add_plotly_eclipse_shapes(self, fig) -> None:
        """Add eclipse region shapes to plotly figure."""
        shapes = []
        in_eclipse = False
        eclipse_start = 0
        
        for i, sunlight in enumerate(self.in_sunlight):
            if not sunlight and not in_eclipse:
                eclipse_start = self.time_min[i]
                in_eclipse = True
            elif sunlight and in_eclipse:
                shapes.append(dict(
                    type="rect",
                    xref="x",
                    yref="paper",
                    x0=eclipse_start,
                    x1=self.time_min[i],
                    y0=0,
                    y1=1,
                    fillcolor=self.COLORS['eclipse'],
                    opacity=0.2,
                    layer="below",
                    line_width=0
                ))
                in_eclipse = False
        
        if in_eclipse:
            shapes.append(dict(
                type="rect",
                xref="x",
                yref="paper",
                x0=eclipse_start,
                x1=self.time_min[-1],
                y0=0,
                y1=1,
                fillcolor=self.COLORS['eclipse'],
                opacity=0.2,
                layer="below",
                line_width=0
            ))
        
        fig.update_layout(shapes=shapes)
    
    def save_all_plots(self, output_dir: str, prefix: str = "sim") -> List[str]:
        """
        Save all standard plots to files.
        
        Args:
            output_dir: Output directory
            prefix: Filename prefix
            
        Returns:
            List of created file paths
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        files = []
        
        # Matplotlib plots
        self.plot_overview(save_path=output_path / f"{prefix}_overview.png", show=False)
        files.append(str(output_path / f"{prefix}_overview.png"))
        
        self.plot_battery_detail(save_path=output_path / f"{prefix}_battery.png", show=False)
        files.append(str(output_path / f"{prefix}_battery.png"))
        
        self.plot_power_breakdown(save_path=output_path / f"{prefix}_power.png", show=False)
        files.append(str(output_path / f"{prefix}_power.png"))
        
        # Plotly HTML
        try:
            import plotly.io as pio
            fig = self.plot_interactive_overview()
            pio.write_html(fig, output_path / f"{prefix}_interactive.html")
            files.append(str(output_path / f"{prefix}_interactive.html"))
        except ImportError:
            pass
        
        return files





