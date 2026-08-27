interface FilmWithScrapeStatus {
  primary_item: {
    metadata: {
      scrape_status: string;
    };
  };
}

export function getLibraryAttentionCounts(
  films: FilmWithScrapeStatus[],
  rootVideoCount: number,
) {
  return {
    metadataReviews: films.filter(
      (film) => film.primary_item.metadata.scrape_status === "needs_review",
    ).length,
    rootVideos: Math.max(0, rootVideoCount),
  };
}
