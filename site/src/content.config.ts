import { defineCollection } from 'astro:content'
import { glob } from 'astro/loaders'
import { docsLoader } from '@astrojs/starlight/loaders'
import { docsSchema } from '@astrojs/starlight/schema'

export const collections = {
  docs: defineCollection({ loader: docsLoader(), schema: docsSchema() }),
  // one file per sponsor track, written by scripts/generate.py from docs/story.md
  tracks: defineCollection({ loader: glob({ pattern: '*.md', base: './src/content/tracks' }) }),
}
