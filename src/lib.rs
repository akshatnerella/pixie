pub mod gateway;
pub mod web;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EmotionState {
    Idle,
    Success,
    Error,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Event {
    Tick,
    WorkSucceeded,
    WorkFailed,
    Reset,
}

pub fn transition(current: EmotionState, event: Event) -> EmotionState {
    match (current, event) {
        (_, Event::WorkSucceeded) => EmotionState::Success,
        (_, Event::WorkFailed) => EmotionState::Error,
        (EmotionState::Error, Event::Tick) => EmotionState::Error,
        (_, Event::Tick | Event::Reset) => EmotionState::Idle,
    }
}

pub fn event_for_tick(tick: u64) -> Event {
    if tick % 12 == 0 {
        Event::Reset
    } else if tick % 7 == 0 {
        Event::WorkFailed
    } else if tick % 4 == 0 {
        Event::WorkSucceeded
    } else {
        Event::Tick
    }
}

#[cfg(test)]
mod tests {
    use super::{transition, EmotionState, Event};

    #[test]
    fn success_event_sets_success_state() {
        assert_eq!(
            transition(EmotionState::Idle, Event::WorkSucceeded),
            EmotionState::Success
        );
    }

    #[test]
    fn error_event_sets_error_state() {
        assert_eq!(
            transition(EmotionState::Success, Event::WorkFailed),
            EmotionState::Error
        );
    }

    #[test]
    fn error_state_sticks_on_tick_until_reset() {
        assert_eq!(
            transition(EmotionState::Error, Event::Tick),
            EmotionState::Error
        );
        assert_eq!(
            transition(EmotionState::Error, Event::Reset),
            EmotionState::Idle
        );
    }
}
