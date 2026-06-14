// charts.js — themed ECharts wrappers

const PALETTE = ['#C7A65A', '#64A7A0', '#8CBF75', '#D58A4B', '#DF6A61', '#A18BCE', '#7A94B8'];

const BASE = {
  textStyle: { color: '#F2F0E8', fontFamily: 'ui-sans-serif' },
  color: PALETTE,
  grid: { left: 38, right: 14, top: 28, bottom: 26, containLabel: true },
  animation: true,
  animationDuration: 760,
  animationEasing: 'cubicOut',
  animationDurationUpdate: 420,
  animationEasingUpdate: 'cubicOut',
};

const X_AXIS = {
  axisLine:  { lineStyle: { color: '#2B2C30' } },
  axisLabel: { color: '#A5A196' },
  axisTick:  { show: false },
};

const Y_AXIS = {
  axisLine:  { show: false },
  axisTick:  { show: false },
  splitLine: { lineStyle: { color: '#2B2C30' } },
  axisLabel: { color: '#A5A196' },
};

const TOOLTIP = {
  trigger: 'axis',
  backgroundColor: '#161719',
  borderColor: '#3A3B41',
  borderWidth: 1,
  textStyle: { color: '#F2F0E8', fontFamily: 'ui-sans-serif', fontSize: 12 },
  padding: [8, 12],
};

function mount(el) {
  const c = echarts.init(el, null, { renderer: 'svg' });
  window.addEventListener('resize', () => c.resize());
  return c;
}

export function lineChart(el, { x, series }) {
  const c = mount(el);
  c.setOption({
    ...BASE,
    tooltip: TOOLTIP,
    legend: { textStyle: { color: '#A5A196' }, top: 0, right: 0, icon: 'roundRect', itemWidth: 8, itemHeight: 8 },
    xAxis: { ...X_AXIS, type: 'category', data: x, boundaryGap: false },
    yAxis: { ...Y_AXIS, type: 'value' },
    series: series.map((s, idx) => ({
      ...s, type: 'line', smooth: true, showSymbol: false,
      areaStyle: { opacity: 0.12 }, lineStyle: { width: 2 },
      animationDelay: idx => idx * 16,
    })),
  });
  return c;
}

export function barChart(el, { categories, values, color }) {
  const c = mount(el);
  c.setOption({
    ...BASE,
    tooltip: { ...TOOLTIP, axisPointer: { type: 'shadow' } },
    xAxis: { ...X_AXIS, type: 'category', data: categories, axisLabel: { ...X_AXIS.axisLabel, interval: 0, rotate: categories.length > 5 ? 25 : 0 } },
    yAxis: { ...Y_AXIS, type: 'value' },
    series: [{
      type: 'bar', data: values,
      itemStyle: { color: color || PALETTE[0], borderRadius: [4, 4, 0, 0] },
      barMaxWidth: 32,
      animationDelay: idx => idx * 22,
      animationDelayUpdate: idx => idx * 8,
    }],
  });
  return c;
}

export function stackedBarChart(el, { categories, series, formatter }) {
  const c = mount(el);
  c.setOption({
    ...BASE,
    tooltip: {
      ...TOOLTIP,
      axisPointer: { type: 'shadow' },
      valueFormatter: formatter || (v => Number(v).toLocaleString()),
    },
    legend: {
      textStyle: { color: '#A5A196' },
      top: 0, right: 0, icon: 'roundRect',
      itemWidth: 8, itemHeight: 8,
    },
    xAxis: {
      ...X_AXIS, type: 'category', data: categories,
      axisLabel: { ...X_AXIS.axisLabel, interval: categories.length > 20 ? 'auto' : 0, rotate: categories.length > 12 ? 45 : 0 },
    },
    yAxis: { ...Y_AXIS, type: 'value' },
    series: series.map((s, i) => ({
      name: s.name,
      type: 'bar',
      stack: 'total',
      data: s.values,
      itemStyle: { color: s.color || PALETTE[i % PALETTE.length] },
      barMaxWidth: 24,
      emphasis: { focus: 'series' },
      animationDelay: idx => idx * 14 + i * 80,
      animationDelayUpdate: idx => idx * 5,
    })),
  });
  return c;
}

export function groupedBarChart(el, { categories, series, formatter }) {
  const c = mount(el);
  c.setOption({
    ...BASE,
    tooltip: {
      ...TOOLTIP,
      axisPointer: { type: 'shadow' },
      valueFormatter: formatter || (v => Number(v).toLocaleString()),
    },
    legend: {
      textStyle: { color: '#A5A196' },
      top: 0, right: 0, icon: 'roundRect',
      itemWidth: 8, itemHeight: 8,
    },
    xAxis: {
      ...X_AXIS, type: 'category', data: categories,
      axisLabel: { ...X_AXIS.axisLabel, interval: 0, rotate: categories.length > 5 ? 25 : 0 },
    },
    yAxis: { ...Y_AXIS, type: 'value' },
    series: series.map((s, i) => ({
      name: s.name,
      type: 'bar',
      data: s.values,
      itemStyle: { color: s.color || PALETTE[i % PALETTE.length], borderRadius: [4, 4, 0, 0] },
      barMaxWidth: 24,
      emphasis: { focus: 'series' },
      animationDelay: idx => idx * 18 + i * 90,
      animationDelayUpdate: idx => idx * 5,
    })),
  });
  return c;
}

export function donutChart(el, data, colors = PALETTE) {
  const c = mount(el);
  c.setOption({
    color: colors,
    tooltip: {
      trigger: 'item',
      backgroundColor: '#161719', borderColor: '#3A3B41', borderWidth: 1,
      textStyle: { color: '#F2F0E8', fontFamily: 'ui-sans-serif' },
      formatter: p => `${p.name}<br/><b>${Number(p.value).toLocaleString()}</b> tokens (${p.percent.toFixed(1)}%)`,
    },
    legend: {
      textStyle: { color: '#A5A196' },
      bottom: 10, icon: 'roundRect', itemWidth: 8, itemHeight: 8,
      type: 'scroll',
    },
    series: [{
      type: 'pie',
      animationType: 'scale',
      animationDuration: 820,
      animationEasing: 'cubicOut',
      center: ['50%', '44%'],
      radius: ['48%', '68%'],
      avoidLabelOverlap: true,
      padAngle: 2,
      itemStyle: { borderColor: '#161719', borderWidth: 2, borderRadius: 4 },
      label: {
        show: true,
        position: 'inside',
        color: '#fff',
        fontSize: 12,
        fontWeight: 600,
        formatter: ({ percent }) => percent >= 6 ? percent.toFixed(0) + '%' : '',
      },
      labelLine: { show: false },
      data,
    }],
  });
  return c;
}
