from typing import List, Dict, Tuple
import os

from torch.distributed import rpc
import torch.distributed as dist

from colossalai.tensor import ProcessGroup


class PipelineProcessGroup:
    # TODO : flexible API for DP size and TP size
    # In the future design mode, dp_degree and tp_degree should be removed
    def __init__(self,
                 rank: int,
                 world_size: int,
                 dp_degree: int = 1,
                 tp_degree: int = 1,
                 num_worker_threads: int = 1,
                 device: str = "cuda") -> None:
        device_mesh_size = dp_degree * tp_degree
        assert world_size % device_mesh_size == 0, "world_size must be the multiple of dp_degree * tp_degree !!!"
        self._num_worker_threads = num_worker_threads

        self._device_mesh_size = device_mesh_size
        self._rank = rank
        self._world_size = world_size
        self._dp_degree = dp_degree
        self._tp_degree = tp_degree
        self.device = device
        self._stage_num = world_size // device_mesh_size
        self._pp_rank = rank // device_mesh_size
        self._pp_ranks = [(rank % device_mesh_size) + i * device_mesh_size for i in range(self._stage_num)]
        self._local_stage_ranks = [(rank // device_mesh_size * device_mesh_size) + i for i in range(device_mesh_size)]

        # pp_ranks
        self._initialize_pp_process_group()

        # initialise tp dp process groups
        self._initialize_tp_dp_process_group()

        # status
        self._is_first_pp_rank = self._pp_rank == 0
        self._is_last_pp_rank = self._pp_rank == self._stage_num - 1

    def _initialize_process_group(self):
        stage_num = self.get_stage_num()
        if stage_num == 1:
            return
        device = self.device
        world_size = self.get_world_size()
        rank = self.get_global_rank()
        backend = 'nccl' if device == 'cuda' else 'gloo'
        dist.init_process_group(backend, world_size=world_size, rank=rank, group_name='main_group')

    def _initialize_pp_process_group(self) -> None:
        rank = self.get_global_rank()
        world_size = self.get_world_size()

        # build rpc connection
        options = rpc.TensorPipeRpcBackendOptions(num_worker_threads=self._num_worker_threads)

        for pp_rank in self._pp_ranks:
            options.set_device_map(f'work{pp_rank}', {rank: pp_rank})

        rpc.init_rpc(name=f'work{rank}', rank=rank, world_size=world_size, rpc_backend_options=options)

    def _initialize_tp_dp_process_group(self) -> None:
        rank = self.get_global_rank()
        local_stage_ranks = self.get_local_stage_global_ranks()
        dp_degree = self.get_dp_degree()
        tp_degree = self.get_tp_degree()
        self._tp_dp_process_group = ProcessGroup(rank, local_stage_ranks, tp_degree, dp_degree)

    def get_global_rank(self):
        return self._rank

    def get_world_size(self):
        return self._world_size

    def get_dp_degree(self) -> int:
        return self._dp_degree

    def get_tp_degree(self) -> int:
        return self._tp_degree

    def get_local_device_mesh_size(self) -> int:
        return self._device_mesh_size

    def get_stage_num(self) -> int:
        return self._stage_num

    def is_first_stage(self) -> bool:
        return self._is_first_pp_rank

    def is_last_stage(self) -> bool:
        return self._is_last_pp_rank

    def check_pp_rank_valid(self, pp_rank: int) -> bool:
        return -1 < pp_rank < self._stage_num

    def get_local_pp_rank(self) -> int:
        return self._pp_rank

    def get_prev_pp_rank(self) -> int:
        prev_pp_rank = self._pp_rank - 1
        if not self.check_pp_rank_valid(prev_pp_rank):
            assert ValueError(f"current rank's pp_rank: {self._pp_rank} doesn't have a previous stage!")
        return prev_pp_rank

    def get_next_pp_rank(self) -> int:
        next_pp_rank = self._pp_rank + 1
        if not self.check_pp_rank_valid(next_pp_rank):
            assert ValueError(f"current rank's pp_rank: {self._pp_rank} doesn't have a next stage!")
        return next_pp_rank

    def get_local_stage_global_ranks(self) -> List[int]:
        return self._local_stage_ranks

    def local_dp_rank(self) -> int:
        return self._tp_dp_process_group.dp_local_rank()

    def local_tp_rank(self) -> int:
        return self._tp_dp_process_group.tp_local_rank()

    def get_pp_global_ranks(self) -> int:
        return self._pp_ranks

    def get_dp_global_ranks(self):
        pass

    def get_tp_global_ranks(self):
        pass
