import { computed } from "vue";
import { tokens } from "../generated/tokens";
import { useAppTheme } from "./useAppTheme";

export type ChartTone = "accent" | "red" | "violet";

const TONE_TOKEN: Record<ChartTone, string> = {
  accent: "surface-accent-6",
  red: "ink-red-6",
  violet: "ink-violet-6",
};

function alpha(hex: string, a: number) {
  const n = (i: number) => parseInt(hex.slice(i, i + 2), 16);
  return `rgba(${n(1)},${n(3)},${n(5)},${a})`;
}

// ECharts cannot read CSS variables, so charts take resolved values and redraw when the scheme flips.
export function useChartTheme() {
  const { resolvedColorScheme: mode } = useAppTheme();
  const palette = computed(() => tokens[mode.value] as Record<string, string>);

  return {
    mode,
    series: computed(() => tokens.chart.series[mode.value]),
    ui: computed(() => tokens.chart.ui[mode.value]),
    tone: (tone: ChartTone) => palette.value[TONE_TOKEN[tone]],
    lineTone: (tone: ChartTone) => {
      const lineColor = palette.value[TONE_TOKEN[tone]];
      return {
        lineColor,
        gradientColor: {
          start: alpha(lineColor, 0.55),
          end: alpha(lineColor, 0),
        },
      };
    },
  };
}
