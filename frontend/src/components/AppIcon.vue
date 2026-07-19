<script setup>
defineProps({
  name: { type: String, required: true },
  size: { type: [Number, String], default: 20 },
  strokeWidth: { type: [Number, String], default: 1.8 },
})

const paths = {
  grid: ['M4 4h6v6H4z', 'M14 4h6v6h-6z', 'M4 14h6v6H4z', 'M14 14h6v6h-6z'],
  flow: ['M6 3v12', 'M18 9v12', 'M6 15c0 3 2 4 5 4h7', 'M3 6l3-3 3 3', 'M15 18l3 3 3-3'],
  database: ['M4 6c0 2 16 2 16 0s-16-2-16 0', 'M4 6v6c0 2 16 2 16 0V6', 'M4 12v6c0 2 16 2 16 0v-6'],
  upload: ['M12 16V4', 'M7 9l5-5 5 5', 'M5 20h14'],
  search: ['M11 18a7 7 0 1 1 0-14 7 7 0 0 1 0 14Z', 'm20 20-4-4'],
  chevron: ['m9 18 6-6-6-6'],
  arrow: ['M5 12h14', 'm14 7 5 5-5 5'],
  spark: ['m12 3-1.4 4.1L7 8.5l3.6 1.6L12 14l1.4-3.9L17 8.5l-3.6-1.4L12 3Z', 'm5 15-.8 2.2L2 18l2.2.8L5 21l.8-2.2L8 18l-2.2-.8L5 15Z'],
  shield: ['M12 3 5 6v5c0 4.7 2.8 8 7 10 4.2-2 7-5.3 7-10V6l-7-3Z', 'm9 12 2 2 4-4'],
  balance: ['M12 3v18', 'M5 7h14', 'm7 0-4 7h8L7 7Z', 'm10 0-4 7h8l-4-7Z'],
  rocket: ['M14 5c2.5-2.5 5.5-2 5.5-2s.5 3-2 5.5l-4 4-4-4 4.5-4.5Z', 'm9.5 8.5-4 1-2.5 2.5 4.5.5', 'm13.5 12.5-1 4L10 19l-1-4.5', 'M6 16c-2 0-3 1-3 3 2 0 3-1 3-3Z'],
  warning: ['M12 4 3 20h18L12 4Z', 'M12 9v5', 'M12 17h.01'],
  check: ['m5 12 4 4L19 6'],
  user: ['M20 21a8 8 0 0 0-16 0', 'M12 13a5 5 0 1 0 0-10 5 5 0 0 0 0 10Z'],
  cpu: ['M9 9h6v6H9z', 'M4 9h2', 'M4 15h2', 'M18 9h2', 'M18 15h2', 'M9 4v2', 'M15 4v2', 'M9 18v2', 'M15 18v2', 'M6 6h12v12H6z'],
  bot: ['M8 8h8a4 4 0 0 1 4 4v6H4v-6a4 4 0 0 1 4-4Z', 'M9 13h.01', 'M15 13h.01', 'M12 8V4', 'M10 4h4'],
  layers: ['m12 3-9 5 9 5 9-5-9-5Z', 'm3 12 9 5 9-5', 'm3 4 9 5 9-5'],
  target: ['M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z', 'M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10Z', 'M12 13a1 1 0 1 0 0-2 1 1 0 0 0 0 2Z'],
  code: ['m8 9-4 3 4 3', 'm16 9 4 3-4 3', 'm14 5-4 14'],
  close: ['M6 6l12 12', 'M18 6 6 18'],
  download: ['M12 4v12', 'm7 11 5 5 5-5', 'M5 20h14'],
}
</script>

<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    :stroke-width="strokeWidth"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <path v-for="path in paths[name] || paths.grid" :key="path" :d="path" />
  </svg>
</template>
