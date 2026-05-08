import useSWR from "swr";
import API from "@/lib/api";

interface DirectoryData {
  current_path: string;
  parent_path: string | null;
  directories: {
    name: string;
    path: string;
  }[];
}

export function useDirectories(path: string, enabled: boolean) {
  return useSWR<DirectoryData>(
    enabled
      ? `${API.systemListDirs()}?path=${encodeURIComponent(path)}`
      : null
  );
}
