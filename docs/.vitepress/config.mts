import { defineConfig } from 'vitepress'

export default defineConfig({
  title: 'paper-rag',
  description: 'RAG over a personal PubMed library, packaged as a Claude Code plugin',
  // GitHub Pages project-site path — update if the repo is renamed/forked under a
  // different name than "paper-rag".
  base: '/paper-rag/',
  appearance: 'force-dark',
  lastUpdated: true,
  cleanUrls: true,

  head: [
    ['link', { rel: 'icon', type: 'image/png', sizes: '32x32', href: '/paper-rag/favicon-32.png' }],
    ['link', { rel: 'apple-touch-icon', href: '/paper-rag/apple-touch-icon.png' }],
  ],

  themeConfig: {
    logo: '/logo-512.png',
    nav: [
      { text: 'Guide', link: '/guide/getting-started' },
      { text: 'Commands', link: '/reference/cli' },
      { text: 'Concepts', link: '/concepts' },
      { text: 'Workflows', link: '/architecture' },
    ],
    sidebar: {
      '/guide/': [
        {
          text: 'Guide',
          items: [
            { text: 'Getting Started', link: '/guide/getting-started' },
            { text: 'Ingesting Papers', link: '/guide/ingest' },
            { text: 'Searching PubMed', link: '/guide/pubmed-search' },
            { text: 'Asking Questions', link: '/guide/ask' },
            { text: 'Extracting Claims', link: '/guide/extract-claims' },
            { text: 'Concept Graph', link: '/guide/graph' },
            { text: 'Citing & Filtering', link: '/guide/cite-and-mine' },
            { text: 'Tags & Homes', link: '/guide/tags-and-homes' },
            { text: 'Dashboard', link: '/guide/dashboard' },
          ],
        },
      ],
      '/reference/': [
        {
          text: 'Commands',
          items: [{ text: 'CLI Commands', link: '/reference/cli' }],
        },
      ],
    },
    socialLinks: [{ icon: 'github', link: 'https://github.com/christineecker/paper-rag' }],
    search: { provider: 'local' },
    outline: { level: [2, 3] },
  },
})
