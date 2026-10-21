import { notFound } from "next/navigation";
import { collectionHref, validCollection } from "@/lib/collections";
import { parseExploreQuery } from "@/lib/explore";
import { getLocalCollection } from "@/lib/server-api";
import ExploreClient from "../../../ExploreClient";

export default async function CollectionPage({ params, searchParams }: {
  params: Promise<{ locale: string; kind: string; key: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { locale, kind, key } = await params;
  if (!validCollection(kind, key)) notFound();
  const search = await searchParams;
  // Collection identity is the path. Only temporary viewing/sort/page state is read.
  const query = parseExploreQuery({ view: search.view, sort: search.sort, dir: search.dir, offset: search.offset });
  const page = await getLocalCollection(kind, key, query);
  if (!page) notFound();
  return <ExploreClient basePath={collectionHref({ kind, key })} collection={page.collection} locale={locale} query={query} results={page.results} />;
}
