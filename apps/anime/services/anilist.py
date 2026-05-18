import hashlib
import json
import logging

import httpx
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


class AniListError(Exception):
    def __init__(self, errors):
        self.errors = errors
        super().__init__(str(errors))


class AniListClient:
    """
    Cache-first GraphQL client for AniList API.
    All responses are stored in Redis to minimise external calls.
    """
    URL = 'https://graphql.anilist.co'

    # ─── GraphQL Queries ──────────────────────────────────────────

    MEDIA_FRAGMENT = """
    fragment MediaBase on Media {
      id
      title { romaji english native }
      coverImage { large medium color }
      bannerImage
      status
      format
      episodes
      duration
      averageScore
      meanScore
      popularity
      trending
      favourites
      season
      seasonYear
      isAdult
      genres
      siteUrl
      nextAiringEpisode { episode airingAt timeUntilAiring }
    }
    """

    TRENDING_QUERY = """
    query TrendingAnime($page: Int, $perPage: Int) {
      Page(page: $page, perPage: $perPage) {
        pageInfo { total currentPage lastPage hasNextPage perPage }
        media(sort: TRENDING_DESC, type: ANIME, isAdult: false) {
          id
          title { romaji english }
          coverImage { large medium color }
          bannerImage
          status format episodes averageScore trending popularity
          season seasonYear genres
          nextAiringEpisode { episode airingAt timeUntilAiring }
        }
      }
    }
    """

    POPULAR_THIS_SEASON_QUERY = """
    query PopularSeason($season: MediaSeason, $year: Int, $page: Int, $perPage: Int) {
      Page(page: $page, perPage: $perPage) {
        pageInfo { total currentPage lastPage }
        media(
          season: $season seasonYear: $year
          sort: POPULARITY_DESC type: ANIME isAdult: false
        ) {
          id title { romaji english }
          coverImage { large medium color }
          averageScore popularity format status episodes season seasonYear genres
          nextAiringEpisode { episode airingAt }
        }
      }
    }
    """

    AIRING_SCHEDULE_QUERY = """
    query AiringSchedule($weekStart: Int, $weekEnd: Int, $page: Int) {
      Page(page: $page, perPage: 50) {
        pageInfo { total currentPage lastPage hasNextPage }
        airingSchedules(
          airingAt_greater: $weekStart
          airingAt_lesser: $weekEnd
          sort: TIME
        ) {
          id airingAt timeUntilAiring episode
          media {
            id title { romaji english }
            coverImage { large medium color }
            format status averageScore isAdult
          }
        }
      }
    }
    """

    ANIME_DETAIL_QUERY = """
    query AnimeDetail($id: Int) {
      Media(id: $id, type: ANIME) {
        id
        title { romaji english native }
        description(asHtml: false)
        coverImage { large medium color }
        bannerImage
        status format episodes duration
        averageScore meanScore popularity trending favourites
        season seasonYear
        startDate { year month day }
        endDate { year month day }
        genres isAdult siteUrl
        tags { name rank isGeneralSpoiler }
        studios(isMain: true) { nodes { id name siteUrl } }
        externalLinks { id site url icon color language }
        nextAiringEpisode { episode airingAt timeUntilAiring }
        trailer { id site thumbnail }
        recommendations(sort: RATING_DESC, perPage: 10) {
          nodes {
            rating
            mediaRecommendation {
              id title { romaji english }
              coverImage { large medium color }
            }
          }
        }
        characters(sort: ROLE, perPage: 30) {
          edges {
            role
            node {
              id name { full }
              image { medium }
            }
            voiceActors(sort: LANGUAGE) {
              id name { full }
              image { medium }
              languageV2
            }
          }
        }
        relations {
          edges {
            relationType(version: 2)
            node {
              id title { romaji english }
              coverImage { large medium }
              format status type
            }
          }
        }
      }
    }
    """

    SEARCH_QUERY = """
    query SearchAnime(
      $search: String $genres: [String] $format: MediaFormat
      $status: MediaStatus $season: MediaSeason $year: Int
      $sort: [MediaSort] $page: Int $perPage: Int
    ) {
      Page(page: $page, perPage: $perPage) {
        pageInfo { total currentPage lastPage hasNextPage }
        media(
          search: $search genre_in: $genres format: $format
          status: $status season: $season seasonYear: $year
          sort: $sort type: ANIME isAdult: false
        ) {
          id title { romaji english }
          coverImage { large medium color }
          averageScore format status episodes duration season seasonYear genres
          description(asHtml: false)
          nextAiringEpisode { episode airingAt }
          startDate { year month day }
          studios(isMain: true) { nodes { id name } }
        }
      }
    }
    """

    TOP_RATED_QUERY = """
    query TopRated($page: Int, $perPage: Int) {
      Page(page: $page, perPage: $perPage) {
        pageInfo { total currentPage lastPage }
        media(sort: SCORE_DESC, type: ANIME, isAdult: false, averageScore_greater: 75) {
          id title { romaji english }
          coverImage { large medium color }
          bannerImage
          averageScore popularity format status episodes
          season seasonYear genres
          nextAiringEpisode { episode airingAt timeUntilAiring }
        }
      }
    }
    """

    UPCOMING_QUERY = """
    query Upcoming($page: Int, $perPage: Int) {
      Page(page: $page, perPage: $perPage) {
        pageInfo { total currentPage lastPage }
        media(
          sort: POPULARITY_DESC type: ANIME isAdult: false
          status: NOT_YET_RELEASED
        ) {
          id title { romaji english }
          coverImage { large medium color }
          bannerImage
          format status episodes averageScore popularity
          season seasonYear genres
          startDate { year month day }
        }
      }
    }
    """

    GENRE_QUERY = """
    query GenreAnime($genre: String, $page: Int, $perPage: Int) {
      Page(page: $page, perPage: $perPage) {
        pageInfo { total currentPage lastPage }
        media(
          genre: $genre sort: TRENDING_DESC type: ANIME isAdult: false
        ) {
          id title { romaji english }
          coverImage { large medium color }
          averageScore popularity format status episodes
          season seasonYear genres
        }
      }
    }
    """

    ALL_GENRES_QUERY = """
    query AllGenres {
      GenreCollection
    }
    """

    # ─── Internals ────────────────────────────────────────────────

    def _cache_key(self, query: str, variables: dict) -> str:
        raw = query + json.dumps(variables, sort_keys=True)
        return f"anilist:{hashlib.md5(raw.encode()).hexdigest()}"

    def _query(self, query: str, variables: dict = None, ttl: int = None) -> dict:
        variables = variables or {}
        ttl = ttl if ttl is not None else settings.ANILIST_CACHE_TTL
        cache_key = self._cache_key(query, variables)

        cached = cache.get(cache_key)
        if cached is not None:
            logger.debug("AniList cache HIT: %s", cache_key[:16])
            return cached

        try:
            response = httpx.post(
                self.URL,
                json={'query': query, 'variables': variables},
                headers={
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                },
                timeout=15.0,
            )
            response.raise_for_status()
        except httpx.TimeoutException:
            logger.error("AniList API timeout")
            raise
        except httpx.HTTPStatusError as e:
            logger.error("AniList HTTP error %s: %s", e.response.status_code, e)
            raise

        data = response.json()
        if 'errors' in data:
            logger.error("AniList GraphQL errors: %s", data['errors'])
            raise AniListError(data['errors'])

        result = data['data']
        cache.set(cache_key, result, ttl)
        return result

    # ─── Public API ───────────────────────────────────────────────

    def get_trending(self, page: int = 1, per_page: int = 20) -> dict:
        return self._query(
            self.TRENDING_QUERY,
            {'page': page, 'perPage': per_page},
        )

    def get_popular_this_season(self, season: str, year: int, page: int = 1, per_page: int = 20) -> dict:
        return self._query(
            self.POPULAR_THIS_SEASON_QUERY,
            {'season': season, 'year': year, 'page': page, 'perPage': per_page},
        )

    def get_airing_schedule(self, week_start: int, week_end: int, page: int = 1) -> dict:
        return self._query(
            self.AIRING_SCHEDULE_QUERY,
            {'weekStart': week_start, 'weekEnd': week_end, 'page': page},
            ttl=settings.ANILIST_AIRING_CACHE_TTL,
        )

    def get_anime_detail(self, anilist_id: int) -> dict:
        return self._query(
            self.ANIME_DETAIL_QUERY,
            {'id': anilist_id},
            ttl=settings.ANILIST_DETAIL_CACHE_TTL,
        )

    def search(self, search: str = None, genres: list = None, format: str = None,
               status: str = None, season: str = None, year: int = None,
               sort: list = None, page: int = 1, per_page: int = 20) -> dict:
        variables = {
            'page': page,
            'perPage': per_page,
            'sort': sort or ['TRENDING_DESC'],
        }
        if search:
            variables['search'] = search
        if genres:
            variables['genres'] = genres
        if format:
            variables['format'] = format
        if status:
            variables['status'] = status
        if season:
            variables['season'] = season
        if year:
            variables['year'] = year
        return self._query(self.SEARCH_QUERY, variables, ttl=60 * 30)

    def get_top_rated(self, page: int = 1, per_page: int = 20) -> dict:
        return self._query(
            self.TOP_RATED_QUERY,
            {'page': page, 'perPage': per_page},
            ttl=60 * 60 * 3,
        )

    def get_upcoming(self, page: int = 1, per_page: int = 15) -> dict:
        return self._query(
            self.UPCOMING_QUERY,
            {'page': page, 'perPage': per_page},
            ttl=60 * 60 * 6,
        )

    def get_genre_anime(self, genre: str, page: int = 1, per_page: int = 10) -> dict:
        return self._query(
            self.GENRE_QUERY,
            {'genre': genre, 'page': page, 'perPage': per_page},
            ttl=60 * 60 * 2,
        )

    MEDIA_REVIEWS_QUERY = """
    query MediaReviews($id: Int) {
      Media(id: $id) {
        reviews(limit: 5, sort: RATING_DESC) {
          nodes {
            id summary rating score
            user { name avatar { medium } }
            createdAt
            body(asHtml: false)
          }
        }
      }
    }
    """

    def get_media_reviews(self, media_id: int) -> dict:
        return self._query(
            self.MEDIA_REVIEWS_QUERY,
            {'id': media_id},
            ttl=60 * 60 * 2,
        )

    def get_all_genres(self) -> list:
        data = self._query(self.ALL_GENRES_QUERY, ttl=60 * 60 * 24)
        return data.get('GenreCollection', [])

    CHARACTER_QUERY = """
    query Character($id: Int) {
      Character(id: $id) {
        id name { full native alternative }
        image { large medium }
        description(asHtml: false)
        gender dateOfBirth { year month day }
        age
        bloodType
        siteUrl
        favourites
        media(page: 1, perPage: 25, sort: POPULARITY_DESC) {
          edges {
            characterRole
            voiceActors(sort: LANGUAGE) {
              id name { full }
              image { medium }
              languageV2
            }
            node {
              id title { romaji english }
              coverImage { large medium }
              format type
            }
          }
        }
      }
    }
    """

    def get_character(self, character_id: int) -> dict:
        return self._query(self.CHARACTER_QUERY, {'id': character_id}, ttl=60 * 60 * 6)

    STAFF_QUERY = """
    query Staff($id: Int) {
      Staff(id: $id) {
        id name { full native alternative }
        image { large medium }
        description(asHtml: false)
        primaryOccupations
        gender dateOfBirth { year month day }
        age yearsActive bloodType
        homeTown
        siteUrl
        favourites
        staffMedia(page: 1, perPage: 25, sort: POPULARITY_DESC) {
          nodes {
            id title { romaji english }
            coverImage { large medium }
            format type
          }
        }
        characters(page: 1, perPage: 20, sort: FAVOURITES_DESC) {
          nodes {
            id name { full }
            image { medium }
          }
        }
      }
    }
    """

    def get_staff(self, staff_id: int) -> dict:
        return self._query(self.STAFF_QUERY, {'id': staff_id}, ttl=60 * 60 * 6)


# Module-level singleton
anilist_client = AniListClient()
