from django.contrib import admin

from .models import (
    Tournament,
    TournamentPhase,
    CompetitionGroup,
    GroupMembership,
    Team,
    Match,
    Player,
)


class GroupMembershipInline(admin.TabularInline):
    model = GroupMembership
    extra = 0


class CompetitionGroupInline(admin.TabularInline):
    model = CompetitionGroup
    extra = 0


class TournamentPhaseInline(admin.TabularInline):
    model = TournamentPhase
    extra = 0
    show_change_link = True


@admin.register(Tournament)
class TournamentAdmin(admin.ModelAdmin):
    list_display = ("name", "sport_type", "structure_mode", "status", "start_date")
    list_filter = ("sport_type", "structure_mode", "status")
    inlines = [TournamentPhaseInline]


@admin.register(TournamentPhase)
class TournamentPhaseAdmin(admin.ModelAdmin):
    list_display = ("name", "tournament", "phase_type", "order", "status")
    inlines = [CompetitionGroupInline]


@admin.register(CompetitionGroup)
class CompetitionGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "phase", "max_teams")
    inlines = [GroupMembershipInline]
