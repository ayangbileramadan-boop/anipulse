from django.db import models
from django.utils import timezone
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from apps.core.models import TimeStampedModel, Streak, UserFollow, Notification, CharacterFavorite, StaffFavorite


class Genre(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Tag(models.Model):
    name = models.CharField(max_length=200, unique=True)
    is_general_spoiler = models.BooleanField(default=False)

    def __str__(self):
        return self.name


class Studio(models.Model):
    name = models.CharField(max_length=200, unique=True)
    anilist_id = models.IntegerField(unique=True, null=True, blank=True)
    site_url = models.URLField(blank=True)

    def __str__(self):
        return self.name


class Anime(TimeStampedModel):
    class Status(models.TextChoices):
        FINISHED = 'FINISHED', 'Finished'
        RELEASING = 'RELEASING', 'Releasing'
        NOT_YET_RELEASED = 'NOT_YET_RELEASED', 'Not Yet Released'
        CANCELLED = 'CANCELLED', 'Cancelled'
        HIATUS = 'HIATUS', 'Hiatus'

    class Format(models.TextChoices):
        TV = 'TV', 'TV'
        TV_SHORT = 'TV_SHORT', 'TV Short'
        MOVIE = 'MOVIE', 'Movie'
        SPECIAL = 'SPECIAL', 'Special'
        OVA = 'OVA', 'OVA'
        ONA = 'ONA', 'ONA'
        MUSIC = 'MUSIC', 'Music'

    class Season(models.TextChoices):
        WINTER = 'WINTER', 'Winter'
        SPRING = 'SPRING', 'Spring'
        SUMMER = 'SUMMER', 'Summer'
        FALL = 'FALL', 'Fall'

    # Identity
    anilist_id = models.IntegerField(unique=True, db_index=True)
    title_romaji = models.CharField(max_length=500)
    title_english = models.CharField(max_length=500, blank=True)
    title_native = models.CharField(max_length=500, blank=True)
    slug = models.SlugField(max_length=600, unique=True, db_index=True)

    # Media info
    format = models.CharField(max_length=20, choices=Format.choices, blank=True)
    status = models.CharField(max_length=30, choices=Status.choices, blank=True, db_index=True)
    description = models.TextField(blank=True)
    episodes = models.IntegerField(null=True, blank=True)
    duration = models.IntegerField(null=True, blank=True, help_text='Per episode in minutes')
    season = models.CharField(max_length=10, choices=Season.choices, blank=True)
    season_year = models.IntegerField(null=True, blank=True, db_index=True)

    # Dates
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    next_airing_episode = models.IntegerField(null=True, blank=True)
    next_airing_at = models.DateTimeField(null=True, blank=True)

    # Scores & ranking
    average_score = models.FloatField(null=True, blank=True)
    mean_score = models.FloatField(null=True, blank=True)
    popularity = models.IntegerField(null=True, blank=True, db_index=True)
    trending = models.IntegerField(null=True, blank=True, db_index=True)
    favourites = models.IntegerField(null=True, blank=True)

    # Images
    cover_image_large = models.URLField(max_length=500, blank=True)
    cover_image_medium = models.URLField(max_length=500, blank=True)
    cover_image_color = models.CharField(max_length=10, blank=True)
    banner_image = models.URLField(max_length=500, blank=True)

    # Relations
    genres = models.ManyToManyField(Genre, blank=True, related_name='anime')
    tags = models.ManyToManyField(Tag, blank=True, related_name='anime', through='AnimeTag')
    studios = models.ManyToManyField(Studio, blank=True, related_name='anime')

    # Links
    is_adult = models.BooleanField(default=False, db_index=True)
    site_url = models.URLField(blank=True)
    trailer_site = models.CharField(max_length=50, blank=True)
    trailer_id = models.CharField(max_length=100, blank=True)
    trailer_thumbnail = models.URLField(max_length=500, blank=True)

    # Sync tracking
    last_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-trending', '-popularity']
        indexes = [
            models.Index(fields=['status', 'season_year']),
            models.Index(fields=['format', 'status']),
            models.Index(fields=['is_adult', 'trending']),
        ]

    def __str__(self):
        return self.display_title

    @property
    def display_title(self):
        from apps.core.utils import surrogatefree
        return surrogatefree(self.title_english or self.title_romaji)

    @property
    def trailer_url(self):
        if self.trailer_site == 'youtube' and self.trailer_id:
            return f'https://www.youtube.com/watch?v={self.trailer_id}'
        return ''


class AnimeTag(models.Model):
    anime = models.ForeignKey(Anime, on_delete=models.CASCADE)
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE)
    rank = models.IntegerField(default=0)

    class Meta:
        unique_together = ('anime', 'tag')
        ordering = ['-rank']


class Episode(TimeStampedModel):
    anime = models.ForeignKey(Anime, on_delete=models.CASCADE, related_name='episode_list')
    number = models.IntegerField()
    title = models.CharField(max_length=500, blank=True)
    thumbnail = models.URLField(max_length=500, blank=True)
    air_date = models.DateTimeField(null=True, blank=True)
    duration = models.IntegerField(null=True, blank=True)

    class Meta:
        unique_together = ('anime', 'number')
        ordering = ['number']

    def __str__(self):
        return f"{self.anime} — Ep {self.number}"


class ExternalLink(models.Model):
    anime = models.ForeignKey(Anime, on_delete=models.CASCADE, related_name='external_links')
    site = models.CharField(max_length=100)
    url = models.URLField(max_length=500)
    icon = models.URLField(max_length=500, blank=True)
    color = models.CharField(max_length=10, blank=True)
    language = models.CharField(max_length=50, blank=True)

    class Meta:
        unique_together = ('anime', 'site')
        ordering = ['site']

    def __str__(self):
        return f"{self.anime} — {self.site}"


class Review(TimeStampedModel):
    class Rating(models.IntegerChoices):
        ONE = 1
        TWO = 2
        THREE = 3
        FOUR = 4
        FIVE = 5
        SIX = 6
        SEVEN = 7
        EIGHT = 8
        NINE = 9
        TEN = 10

    anime = models.ForeignKey(Anime, on_delete=models.CASCADE, related_name='reviews')
    user = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='reviews')
    rating = models.IntegerField(choices=Rating.choices)
    title = models.CharField(max_length=200, blank=True)
    body = models.TextField()
    likes = models.PositiveIntegerField(default=0)
    is_spoiler = models.BooleanField(default=False)
    anilist_review_id = models.IntegerField(null=True, blank=True, unique=True)

    class Meta:
        unique_together = ('anime', 'user')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} on {self.anime.display_title}"


class DiscussionThread(TimeStampedModel):
    anime = models.ForeignKey(Anime, on_delete=models.CASCADE, related_name='discussion_threads')
    user = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='discussion_threads')
    title = models.CharField(max_length=300)
    body = models.TextField()
    episode_number = models.IntegerField(null=True, blank=True, help_text='Leave blank for general discussion')
    is_spoiler = models.BooleanField(default=False)
    likes = models.PositiveIntegerField(default=0)
    views = models.PositiveIntegerField(default=0)
    is_pinned = models.BooleanField(default=False)

    class Meta:
        ordering = ['-is_pinned', '-created_at']

    def __str__(self):
        ep = f" (Ep {self.episode_number})" if self.episode_number else ""
        return f"{self.user.username}: {self.title}{ep}"

    @property
    def comment_count(self):
        return self.comments.count()


class DiscussionComment(TimeStampedModel):
    thread = models.ForeignKey(DiscussionThread, on_delete=models.CASCADE, related_name='comments')
    user = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='discussion_comments')
    body = models.TextField()
    is_spoiler = models.BooleanField(default=False)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='replies')
    likes = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.user.username} on {self.thread.title}"


class Battle(models.Model):
    anime1 = models.ForeignKey(Anime, on_delete=models.CASCADE, related_name='battles_as_first')
    anime2 = models.ForeignKey(Anime, on_delete=models.CASCADE, related_name='battles_as_second')
    votes1 = models.PositiveIntegerField(default=0)
    votes2 = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    is_daily_featured = models.BooleanField(default=False)
    expires_at = models.DateTimeField(null=True, blank=True)
    category = models.CharField(max_length=50, default='versus', help_text='versus, villain, opening, etc.')

    class Meta:
        ordering = ['-created_at']

    @property
    def total_votes(self):
        return self.votes1 + self.votes2

    @property
    def pct1(self):
        return round((self.votes1 / self.total_votes) * 100) if self.total_votes else 50

    @property
    def pct2(self):
        return round((self.votes2 / self.total_votes) * 100) if self.total_votes else 50

    @property
    def is_expired(self):
        from django.utils import timezone
        return self.expires_at and timezone.now() >= self.expires_at

    @property
    def time_remaining(self):
        if not self.expires_at:
            return None
        remaining = self.expires_at - timezone.now()
        if remaining.total_seconds() <= 0:
            return None
        return remaining

    def __str__(self):
        return f"{self.anime1} vs {self.anime2}"


class BattleVote(models.Model):
    battle = models.ForeignKey(Battle, on_delete=models.CASCADE, related_name='votes')
    user = models.ForeignKey('users.User', on_delete=models.CASCADE)
    choice = models.IntegerField(help_text='1 or 2 for anime1 or anime2')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('battle', 'user')


class BattleCategoryVote(models.Model):
    CATEGORIES = [
        ('story', 'Story'),
        ('characters', 'Characters'),
        ('animation', 'Animation'),
        ('villains', 'Villains'),
        ('world_building', 'World Building'),
        ('emotional_impact', 'Emotional Impact'),
    ]
    battle = models.ForeignKey(Battle, on_delete=models.CASCADE, related_name='category_votes')
    user = models.ForeignKey('users.User', on_delete=models.CASCADE)
    category = models.CharField(max_length=30, choices=CATEGORIES)
    choice = models.IntegerField(help_text='1 for anime1, 2 for anime2')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('battle', 'user', 'category')


class BattleArgument(models.Model):
    battle = models.ForeignKey(Battle, on_delete=models.CASCADE, related_name='arguments')
    user = models.ForeignKey('users.User', on_delete=models.CASCADE)
    side = models.IntegerField(help_text='1 for anime1, 2 for anime2')
    body = models.TextField(max_length=500)
    votes = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-votes', '-created_at']


class BattleArgumentVote(models.Model):
    argument = models.ForeignKey(BattleArgument, on_delete=models.CASCADE, related_name='user_votes')
    user = models.ForeignKey('users.User', on_delete=models.CASCADE)
    value = models.IntegerField(default=1, help_text='1 for upvote, -1 for downvote')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('argument', 'user')


class TierList(models.Model):
    TIERS = [
        ('S', 'S Tier'),
        ('A', 'A Tier'),
        ('B', 'B Tier'),
        ('C', 'C Tier'),
        ('D', 'D Tier'),
        ('F', 'F Tier'),
    ]
    user = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='tier_lists')
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_public = models.BooleanField(default=True)
    likes = models.PositiveIntegerField(default=0)
    view_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username}: {self.title}"


class TierListItem(models.Model):
    tier_list = models.ForeignKey(TierList, on_delete=models.CASCADE, related_name='items')
    anime = models.ForeignKey(Anime, on_delete=models.CASCADE)
    tier = models.CharField(max_length=2, choices=TierList.TIERS)
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ['tier', 'order']

    def __str__(self):
        return f"{self.anime} - {self.tier}"


class TierListLike(models.Model):
    tier_list = models.ForeignKey(TierList, on_delete=models.CASCADE, related_name='liked_by')
    user = models.ForeignKey('users.User', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('tier_list', 'user')

    def __str__(self):
        return f"{self.user.username} likes {self.tier_list.title}"


class FavoriteAnime(models.Model):
    user = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='favorite_anime')
    anime = models.ForeignKey(Anime, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'anime')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} fav {self.anime}"


class SocialPost(TimeStampedModel):
    POST_TYPES = [
        ('post', 'User Post'),
        ('discussion', 'Discussion'),
        ('episode_discussion', 'Episode Discussion'),
        ('trending', 'Trending Topic'),
        ('seasonal', 'Seasonal Discussion'),
        ('poll', 'Poll'),
        ('qotd', 'Question of the Day'),
        ('hot_take', 'Hot Take'),
        ('recommendation', 'Recommendation Thread'),
        ('share_battle', 'Shared Battle'),
        ('share_tierlist', 'Shared Tier List'),
        ('share_review', 'Shared Review'),
    ]
    user = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='social_posts')
    title = models.CharField(max_length=200, blank=True)
    body = models.TextField(max_length=2000, blank=True)
    post_type = models.CharField(max_length=30, choices=POST_TYPES, default='post')
    anime = models.ForeignKey(Anime, on_delete=models.SET_NULL, null=True, blank=True, related_name='social_posts')
    image = models.URLField(max_length=500, blank=True)
    likes = models.PositiveIntegerField(default=0)
    reply_to = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='replies')
    comments = GenericRelation('Comment', content_type_field='content_type', object_id_field='object_id')
    # Shared content (battles, tierlists, reviews)
    shared_ct = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True, blank=True, related_name='shared_posts')
    shared_id = models.PositiveIntegerField(null=True, blank=True)
    shared_obj = GenericForeignKey('shared_ct', 'shared_id')

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username}: {self.title or self.body[:50]}"

    @property
    def is_share(self):
        return self.post_type in ('share_battle', 'share_tierlist', 'share_review') and self.shared_id is not None


class SocialLike(models.Model):
    post = models.ForeignKey(SocialPost, on_delete=models.CASCADE, related_name='liked_by')
    user = models.ForeignKey('users.User', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('post', 'user')


class UserActivity(TimeStampedModel):
    ACTIVITY_TYPES = [
        ('WATCHING', 'Started Watching'),
        ('COMPLETED', 'Completed'),
        ('PLANNING', 'Plan to Watch'),
        ('REVIEW', 'Wrote a Review'),
        ('ACHIEVEMENT', 'Earned Achievement'),
        ('BATTLE', 'Voted in Battle'),
        ('POST', 'Made a Post'),
        ('STREAK', 'Reached Streak Milestone'),
        ('SHARE', 'Shared Content'),
        ('POLL_VOTE', 'Voted in a Poll'),
    ]
    user = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='activities')
    activity_type = models.CharField(max_length=20, choices=ACTIVITY_TYPES)
    anime = models.ForeignKey(Anime, on_delete=models.SET_NULL, null=True, blank=True)
    description = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username}: {self.activity_type}"


class AnimeTheme(models.Model):
    THEME_TYPES = [
        ('OP', 'Opening'),
        ('ED', 'Ending'),
    ]
    anime = models.ForeignKey(Anime, on_delete=models.CASCADE, related_name='themes')
    theme_type = models.CharField(max_length=3, choices=THEME_TYPES)
    number = models.IntegerField(default=1)
    title = models.CharField(max_length=300, blank=True)
    artist = models.CharField(max_length=300, blank=True)
    video_url = models.URLField(max_length=500, blank=True)
    image_url = models.URLField(max_length=500, blank=True)

    class Meta:
        ordering = ['theme_type', 'number']

    def __str__(self):
        return f"{self.anime} {self.theme_type}{self.number}: {self.title}"


class Comment(models.Model):
    MAX_DEPTH = 3
    user = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='comments')
    body = models.TextField(max_length=2000)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='replies')
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')
    is_spoiler = models.BooleanField(default=False)
    is_edited = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
        ]

    def __str__(self):
        return f"{self.user.username}: {self.body[:50]}"

    @property
    def depth(self):
        d = 0
        p = self.parent
        while p and d < self.MAX_DEPTH:
            d += 1
            p = p.parent
        return d

    @property
    def like_count(self):
        return self.likes.count()

    def can_edit(self, user):
        return user == self.user or user.is_staff


class CommentLike(models.Model):
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, related_name='likes')
    user = models.ForeignKey('users.User', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('comment', 'user')

    def __str__(self):
        return f"{self.user.username} likes {self.comment.id}"


class Poll(models.Model):
    post = models.OneToOneField(SocialPost, on_delete=models.CASCADE, related_name='poll')
    question = models.CharField(max_length=300)
    is_multiple = models.BooleanField(default=False)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.question

    @property
    def total_votes(self):
        return self.options.annotate(vc=models.Count('votes')).aggregate(t=models.Sum('vc'))['t'] or 0


class PollOption(models.Model):
    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name='options')
    text = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return self.text

    @property
    def vote_count(self):
        return self.votes.count()

    @property
    def percentage(self, total=None):
        t = total or self.poll.total_votes
        return round(self.vote_count / t * 100, 1) if t else 0


class PollVote(models.Model):
    option = models.ForeignKey(PollOption, on_delete=models.CASCADE, related_name='votes')
    user = models.ForeignKey('users.User', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('option', 'user')

    def __str__(self):
        return f"{self.user.username} → {self.option.text}"


class Bookmark(models.Model):
    user = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='bookmarks')
    post = models.ForeignKey(SocialPost, on_delete=models.CASCADE, related_name='bookmarks')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'post')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} bookmarked {self.post.id}"
