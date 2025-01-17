def is_learned_based_on_exercise_outcomes(exercise_log, is_productive=True):
    """
    Checks if the user has reported the exercise as too easy or looks into the
    streaks of this exercise log. Currently (14/06/2024), Zeeguu uses 2 cycles of
    4 different days in spaced repetition to consider a word learned.

    If a user has 2 streaks of 4, it means they have completed two full cycles,
    and therefore have learned the word.

    The user also has the option of saying they do not want productive exercises.
    In this case, we only need to have a single streak of 4 to consider the bookmark
    learned.

    :return:Boolean, the bookmark is learned based on the exercises or not.
    """
    if exercise_log.is_empty():
        return False

    if exercise_log.last_exercise().is_too_easy():
        return True

    # For a bookmark to be learned it needs to have 1 or 2 cycles
    # completed depending on the user preference.

    scheduler = exercise_log.bookmark.get_scheduler()

    learning_cycle_length = len(scheduler.get_cooling_interval_dictionary())

    streaks_by_length = exercise_log.exercise_streaks_of_given_length()
    full_cycles_completed = streaks_by_length.get(learning_cycle_length)

    if is_productive:
        return full_cycles_completed == 2
    else:
        return full_cycles_completed == 1
