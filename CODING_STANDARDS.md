# AniPulse Coding Standards

## Frontend Rules

### 1. Flex Children Must Have `min-width: 0`

Every direct child of a `display: flex` container that contains text or shrinkable content MUST have `min-width: 0` (or class `min-w-0` in Bootstrap 5). Without it, flex items default to `min-width: auto`, preventing text truncation and causing overflow.

```html
<!-- WRONG - ellipsis won't activate -->
<div class="d-flex">
  <div class="flex-grow-1 text-truncate">Long text...</div>
</div>

<!-- RIGHT -->
<div class="d-flex">
  <div class="flex-grow-1 text-truncate min-w-0">Long text...</div>
</div>
```

**Anti-bug check**: Every `.d-flex` or `display:flex` container — inspect all children. If a child has `text-truncate`, `text-overflow: ellipsis`, or `white-space: nowrap`, it MUST also have `min-width:0`.

### 2. No Fixed Widths on Mobile (<768px)

Do not set absolute pixel widths that don't adapt to viewport. Use relative units (`%`, `vw`, `fr`, `auto`) or media queries that *reduce* widths on mobile.

```css
/* WRONG - will overflow on 320px phones */
.anime-card { width: 200px; }

/* RIGHT - responsive */
.anime-card { width: 100%; max-width: 200px; }

/* RIGHT - adaptive media query */
.anime-card { width: 200px; }
@media (max-width: 576px) { .anime-card { width: 48%; } }  /* reduces, not fixed */
```

**Anti-bug rule**: If `width: <N>px` appears in a `@media (max-width: ...)` block, the value must be *smaller* than the desktop/default value. Never larger.

### 3. Every Text Container Must Have Overflow Protection

Any element with user-generated or variable-length text MUST have:
```css
overflow: hidden;
text-overflow: ellipsis;
white-space: nowrap;
```
Or use Bootstrap's `.text-truncate` class.

**Exception**: Containers where text is intentionally wrapped (paragraphs, descriptions). These should use `word-break: break-word` or `overflow-wrap: break-word` instead.

**Anti-bug rule**: If a template uses `{{ ...|truncatechars:N }}` without a CSS overflow rule on the parent, it's a violation.

### 4. No Horizontal Scrolling

The viewport must never scroll horizontally. Enforcement:
- No `overflow-x: auto` / `overflow-x: scroll` on the `<body>` or root containers
- Tab bars with `overflow-x: auto` MUST NOT hide the scrollbar (`scrollbar-width: auto` not `none`)
- `white-space: nowrap` on non-fixed containers must have paired `overflow: hidden`
- For horizontal scroll strips (e.g., trending cards), items must reduce width on small viewports so partial-peek doesn't exceed viewport

```css
/* WRONG - invisible scrollbar traps content */
.tab-bar { overflow-x: auto; scrollbar-width: none; }

/* RIGHT - visible scrollbar */
.tab-bar { overflow-x: auto; }
```

**Anti-bug rule**: `scrollbar-width: none` is banned unless paired with JavaScript swipe detection that provides visible indicators.

## Backend Rules

### 5. All Mutating Operations Must Be Atomic

Every view that performs multiple writes (create+notify, update+activity, delete+recalculate) MUST be decorated with `@transaction.atomic`.

```python
# WRONG - partial write on failure
def follow_user(request, username):
    follow = UserFollow.objects.create(follower=request.user, following=target)
    _create_notification(target, f'{request.user} followed you')  # if this fails, follow is orphaned

# RIGHT
@transaction.atomic
def follow_user(request, username):
    follow = UserFollow.objects.create(follower=request.user, following=target)
    _create_notification(target, f'{request.user} followed you')
```

**Anti-bug rule**: If a function does `create()`/`update_or_create()` + any other write operation (another create, save, delete, notification), it needs `@transaction.atomic`.

### 6. Counter Fields Must Use F() Expressions

Every increment/decrement of a numeric counter field MUST use `F()` to prevent race conditions:

```python
# WRONG - race condition under concurrent requests
obj.likes += 1
obj.save()

# RIGHT - atomic increment at database level
MyModel.objects.filter(id=obj.id).update(likes=F('likes') + 1)
```

**Models with counter fields**: `Review.likes`, `SocialPost.likes`, `TierList.likes`, `TierList.view_count`, `DiscussionThread.views`, `WatchlistEntry.episodes_watched`

**Anti-bug rule**: If you see `obj.field += 1` followed by `obj.save()`, it's always wrong. Use `MyModel.objects.filter(id=obj.id).update(field=F('field') + 1)` instead.

### 7. Every User Action Must Create a UserActivity Record

All user-initiated actions must be recorded for the feed and profile activity tab:
- Reviewing, liking, commenting, following, creating tier lists, voting in battles, changing watchlist status, earning achievements

```python
# AFTER every user action:
UserActivity.objects.create(
    user=request.user,
    activity_type='<TYPE>',  # one of: REVIEW, LIKE, COMMENT, FOLLOW, TIER_LIST, BATTLE_VOTE, WATCHING, COMPLETED, ACHIEVEMENT
    anime=<anime_obj or None>,
    description='<human-readable description>',
)
```

**Anti-bug rule**: Every new `@login_required` view that creates/updates data must have a matching `UserActivity.objects.create()` call.

### 8. All List Views Must Be Paginated

Every view that returns a list of items to a template MUST use Django's `Paginator`:

```python
from django.core.paginator import Paginator

paginator = Paginator(queryset, 20)
page = request.GET.get('page', 1)
items = paginator.get_page(page)
```

**Anti-bug rule**: If a view does `.all()` or `.filter()` without `.first()`, `.get()`, or a slice, it must be paginated. Default page size: 20.

### 9. No N+1 Queries

Every queryset that accesses related fields inside a loop (or template loop) MUST use `select_related()` (for FK) or `prefetch_related()` (for reverse FK/M2M):

```python
# WRONG - N+1: each iteration hits DB for entry.anime
for entry in WatchlistEntry.objects.filter(user=user):
    print(entry.anime.title)

# RIGHT
for entry in WatchlistEntry.objects.filter(user=user).select_related('anime'):
    print(entry.anime.title)

# WRONG - N+1 on reverse relation
for entry in entries:
    for genre in entry.anime.genres.all():  # hits DB each time

# RIGHT
for entry in WatchlistEntry.objects.filter(user=user).select_related('anime').prefetch_related('anime__genres'):
    for genre in entry.anime.genres.all():  # cached
```

**Anti-bug rule**: Within `{% for %}` loops in templates, every FK access (`obj.related.field`) must have a corresponding `select_related()` in the view. Every reverse relation must have `prefetch_related()`.

### 10. Feed and List Views Must Be Cached

Feed-style views (feed, battle list, tier list list) MUST use Django's cache framework:

```python
from django.core.cache import cache

def my_list_view(request):
    cache_key = f'my_list_key'  # include user-specific part if personalized
    result = cache.get(cache_key)
    if result is None:
        result = compute_expensive_queryset()
        cache.set(cache_key, result, 300)  # 5-minute TTL
    return render(request, 'template.html', result)
```

**Cache invalidation**: Use signals (`post_save`, `post_delete`) to invalidate related cache keys when data changes.

**Anti-bug rule**: Any view that does 3+ DB queries or joins 3+ tables must be cached unless it's a write operation.

## Architecture Constraints

### File Organization
```
apps/
  core/       — shared models (UserFollow, Streak), profile views, social views
  anime/      — Anime, Review, Comment, Battle, TierList, UserActivity models + services
  watchlist/  — WatchlistEntry, CustomList views + serializers
  feed/       — FeedBuilder service (cache, compose, fallback)
  users/      — Custom User model, auth, profile editing
  api/        — DRF viewsets
```

### Data Flow
```
User Action → View (@transaction.atomic, F() for counters) → 
  Model write + UserActivity.create() → Feed cache invalidation signal →
    FeedBuilder recomposes on next request (cache miss)
```

### Frontend Component Hierarchy
```
base.html (nav, theme toggle, global CSS)
  → social_feed.html (IntersectionObserver infinite scroll, 6 item templates)
  → profile.html (tabbed: watching/completed/favorites/tierlists/activity/reviews)
  → anime_detail.html (detail + comments + characters + reviews)
  → battle/, tierlist/, discover/, dashboard/ (feature pages)
```

### Fallback Chain (Feed)
```
Personalized content → followed user posts → recent activity → 
AniList trending → seasonal anime → most watched → welcome card
```
NEVER show an empty list. Every list view must have a fallback content state.

### Rate Limiting
- Comment creation: 10 requests/minute/IP (existing `@ratelimit` decorator)
- Follow/unfollow: 30/minute/user
- Battle voting: 60/minute/user
- Feed API: 30/minute/user
