# python3
# Copyright 2018 DeepMind Technologies Limited. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""A simple agent-environment training loop."""

import time
from typing import Optional

from acme import core
# Internal imports.
from acme.utils import counting
from acme.utils import loggers

import dm_env


class EnvironmentLoop(core.Worker):
  """A simple RL environment loop.

  This takes `Environment` and `Actor` instances and coordinates their
  interaction. This can be used as:

    loop = EnvironmentLoop(environment, actor)
    loop.run(num_episodes)

  A `Counter` instance can optionally be given in order to maintain counts
  between different Acme components. If not given a local Counter will be
  created to maintain counts between calls to the `run` method.

  A `Logger` instance can also be passed in order to control the output of the
  loop. If not given a platform-specific default logger will be used as defined
  by utils.loggers.make_default_logger. A string `label` can be passed to easily
  change the label associated with the default logger; this is ignored if a
  `Logger` instance is given.
  """

  def __init__(
      self,
      environment: dm_env.Environment,
      actor: core.Actor,
      counter: counting.Counter = None,
      logger: loggers.Logger = None,
      label: str = 'environment_loop',
  ):
    # Internalize agent and environment.
    self._environment = environment
    self._actor = actor
    self._counter = counter or counting.Counter()
    self._logger = logger or loggers.make_default_logger(label)

  def run(self,
          num_episodes: Optional[int] = None,
          num_steps: Optional[int] = None):
    """Perform the run loop.

    Run the environment loop either for `num_episodes` episodes or for at
    least `num_steps` steps (the last episode is always run until completion,
    so the total number of steps may be slightly more than `num_steps`).
    At least one of these two arguments has to be None.
    Each episode is itself a loop which interacts first with the environment to
    get an observation and then give that observation to the agent in order to
    retrieve an action. Upon termination of an episode a new episode will be
    started. If the number of episodes and the number of steps are not given
    then this will interact with the environment infinitely.
    If both num_episodes and num_steps are `None` (default), runs without limit.

    Args:
      num_episodes: number of episodes to run the loop for.
      num_steps: minimal number of steps to run the loop for.

    Raises:
      ValueError: If both 'num_episodes' and 'num_steps' are not None.
    """

    if not (num_episodes is None or num_steps is None):
      raise ValueError('Either "num_episodes" or "num_steps" should be None.')

    def should_terminate(episode_count: int, step_count: int) -> bool:
      return ((num_episodes is not None and episode_count >= num_episodes) or
              (num_steps is not None and step_count >= num_steps))

    episode_count, step_count = 0, 0
    while not should_terminate(episode_count, step_count):
      # Reset any counts and start the environment.
      start_time = time.time()
      episode_steps = 0
      episode_return = 0
      timestep = self._environment.reset()

      # Make the first observation.
      self._actor.observe_first(timestep)

      # Run an episode.
      while not timestep.last():
        # Generate an action from the agent's policy and step the environment.
        action = self._actor.select_action(timestep.observation)
        timestep = self._environment.step(action)

        # Have the agent observe the timestep and let the actor update itself.
        self._actor.observe(action, next_timestep=timestep)
        self._actor.update()

        # Book-keeping.
        episode_steps += 1
        episode_return += timestep.reward

      # Record counts.
      counts = self._counter.increment(episodes=1, steps=episode_steps)

      # Collect the results and combine with counts.
      steps_per_second = episode_steps / (time.time() - start_time)
      result = {
          'episode_length': episode_steps,
          'episode_return': episode_return,
          'steps_per_second': steps_per_second,
      }
      result.update(counts)
      episode_count += 1
      step_count += episode_steps

      # Log the given results.
      self._logger.write(result)


# Internal class.
