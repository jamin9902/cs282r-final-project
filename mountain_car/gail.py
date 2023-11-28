"""
General Adversarial Inverse Learning (GAIL)

The original GAIL paper describes the following main components of their algorithm:
1) input expert trajectories, an initial policy, and discriminator parameters
2) train by:
 i) sampling trajectories from the input expert trajectories
 ii) compute a discriminator update
 iii) compute a policy update

Below, we will indicate which parts corresponds to which of these steps.
"""

import numpy as np
from imitation.policies.serialize import load_policy
from imitation.util.util import make_vec_env
from imitation.data.wrappers import RolloutInfoWrapper

SEED = 42

# env is a vectorized version of the MountainCar environment that tracks 8 instances simultaneously
# the number of instances can be changed by setting n_envs, and n_envs=1 is equivalent to loading MountainCar directly from gymnasium
# we will use this to generate expert trajectories
env = make_vec_env(
    "seals:seals/MountainCar-v0",
    rng=np.random.default_rng(SEED),
    n_envs=8,
    post_wrappers=[
        lambda env, _: RolloutInfoWrapper(env)
    ],  # needed for computing rollouts later
)

# Expert is a pre-trained model loaded from HuggingFace
# if we wanted to train our own expert, we could use Q-learning like in our previous checkpoint
# we will use this to generate expert trajectories
"""
expert = load_policy(
    "ppo-huggingface",
    env_name="seals:seals/MountainCar-v0",
    venv=env,
)
"""
from imitation.data import rollout

# rollouts is a list of generated trajectories from the expert policy with the given environment
# these are the expert demonstrations that we will use for inverse reinforcement learning
# this forms the "expert trajectories" part of the input to GAIL
"""
rollouts = rollout.rollout(
    expert,
    env,
    rollout.make_sample_until(min_timesteps=None, min_episodes=60),
    rng=np.random.default_rng(SEED),
)
"""

from imitation.algorithms.adversarial.gail import GAIL
from imitation.rewards.reward_nets import BasicRewardNet
from imitation.util.networks import RunningNorm
from stable_baselines3 import PPO
from stable_baselines3.ppo import MlpPolicy
from stable_baselines3.common.evaluation import evaluate_policy

# This is a learner that uses the proximal policy optimization algorithm
# this is what we will use to compute the policy update steps of the GAIL algorithm
learner = PPO(
    env=env,
    policy=MlpPolicy,
    batch_size=64,
    ent_coef=0.0,
    learning_rate=0.0004,
    gamma=0.95,
    n_epochs=5,
    seed=SEED,
)

# This is a neural network that takes a batch of (state, action, next_state) triples and calculates the associated rewards
# this acts as the discriminator used in GAIL.
# This is what we will use to compute the discriminator update steps of the GAIL algorithm
# according to the original paper: "The job of D is to distinguish between the distribution of data generated by G and the true
# data distribution. When D cannot distinguish data generated by G from the true data, then G has
# successfully matched the true data."
reward_net = BasicRewardNet(
    observation_space=env.observation_space,
    action_space=env.action_space,
    normalize_input_layer=RunningNorm,
)

import pickle

with open("continuous", "rb") as t:
    rollouts = pickle.load(t)

# Imitation implementation of GAIL 
gail_trainer = GAIL(
    demonstrations=rollouts,
    demo_batch_size=1024,
    gen_replay_buffer_capacity=512,
    n_disc_updates_per_round=8,
    venv=env,
    gen_algo=learner,
    reward_net=reward_net,
)

# Evaluate the learner before we have done any training to get a baseline estimate of performance
env.seed(SEED)
learner_rewards_before_training, _ = evaluate_policy(
    learner, env, 100, return_episode_rewards=True
)

# Train the learner by making 80000 GAIL steps
gail_trainer.train(800_000)

# Evaluate the learner after training to determine how much performance has improved
env.seed(SEED)
learner_rewards_after_training, _ = evaluate_policy(
    learner, env, 100, return_episode_rewards=True
)