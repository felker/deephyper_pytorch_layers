import time
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from load_torch import cuda_vs_knl, use_knl  # noqa


def run(point):
    start = time.time()
    try:
        batch_size = point["batch_size"]
        image_size = point["image_size"]
        conv1_in_chan = point["conv1_in_chan"]
        conv1_out_chan = point["conv1_out_chan"]
        conv1_kern = point["conv1_kern"]
        pool_size = point["pool_size"]
        conv2_out_chan = point["conv2_out_chan"]
        conv2_kern = point["conv2_kern"]
        fc1_out = point["fc1_out"]
        fc2_out = point["fc2_out"]
        fc3_out = point["fc3_out"]
        print(point)
        import torch

        device, dtype = cuda_vs_knl(point)

        class Net(torch.nn.Module):
            def __init__(
                self,
                batch_size,
                image_size,
                conv1_in_chan,
                conv1_out_chan,
                conv1_kern,
                pool_size,
                conv2_out_chan,
                conv2_kern,
                fc1_out,
                fc2_out,
                fc3_out,
            ):
                super(Net, self).__init__()
                self.flop = 0
                self.conv1 = torch.nn.Conv2d(
                    conv1_in_chan, conv1_out_chan, conv1_kern
                ).to(device, dtype=dtype)
                self.flop += (
                    conv1_kern ** 2
                    * conv1_in_chan
                    * conv1_out_chan
                    * image_size ** 2
                    * batch_size
                )
                print(self.flop)
                self.pool = torch.nn.MaxPool2d(pool_size, pool_size).to(
                    device, dtype=dtype
                )
                self.flop += image_size ** 2 * conv1_out_chan * batch_size
                self.conv2 = torch.nn.Conv2d(
                    conv1_out_chan, conv2_out_chan, conv2_kern
                ).to(device, dtype=dtype)
                self.flop += (
                    conv2_kern ** 2
                    * conv1_out_chan
                    * conv2_out_chan
                    * int(image_size / pool_size) ** 2
                    * batch_size
                )
                print(self.flop)
                self.view_size = conv2_out_chan * conv2_kern * conv2_kern
                self.fc1 = torch.nn.Linear(
                    conv2_out_chan * conv2_kern * conv2_kern, fc1_out
                ).to(device, dtype=dtype)
                self.flop += (2 * self.view_size - 1) * fc1_out * batch_size
                self.fc2 = torch.nn.Linear(fc1_out, fc2_out).to(device, dtype=dtype)
                self.flop += (2 * fc1_out - 1) * fc2_out * batch_size
                self.fc3 = torch.nn.Linear(fc2_out, fc3_out).to(device, dtype=dtype)
                self.flop += (2 * fc2_out - 1) * fc3_out * batch_size

            def forward(self, x):
                x = self.pool(torch.nn.functional.relu(self.conv1(x)))
                x = self.pool(torch.nn.functional.relu(self.conv2(x)))
                x = x.view(-1, self.view_size)
                x = torch.nn.functional.relu(self.fc1(x))
                x = torch.nn.functional.relu(self.fc2(x))
                x = self.fc3(x)
                return x

        inputs = torch.arange(
            batch_size * image_size ** 2 * conv1_in_chan, dtype=dtype, device=device
        ).view((batch_size, conv1_in_chan, image_size, image_size))
        net = Net(
            batch_size,
            image_size,
            conv1_in_chan,
            conv1_out_chan,
            conv1_kern,
            pool_size,
            conv2_out_chan,
            conv2_kern,
            fc1_out,
            fc2_out,
            fc3_out,
        )
        outputs = net(inputs)

        total_flop = net.flop

        runs = 5
        tot_time = 0.0
        tt = time.time()
        for _ in range(runs):
            outputs = net(inputs)  # noqa: F841
            tot_time += time.time() - tt
            tt = time.time()

        ave_time = tot_time / runs

        print("total_flop = ", total_flop, "ave_time = ", ave_time)

        ave_flops = total_flop / ave_time
        runtime = time.time() - start
        print("runtime=", runtime, "ave_flops=", ave_flops)

        return ave_flops
    except Exception as e:
        import traceback

        print("received exception: ", str(e), "for point: ", point)
        print(traceback.print_exc())
        print("runtime=", time.time() - start)
        return 0.0


if __name__ == "__main__":
    point = {
        "batch_size": 10,
        "image_size": 32,
        "conv1_in_chan": 3,
        "conv1_out_chan": 6,
        "conv1_kern": 5,
        "pool_size": 2,
        "conv2_out_chan": 16,
        "conv2_kern": 5,
        "fc1_out": 120,
        "fc2_out": 84,
        "fc3_out": 10,
    }

    if use_knl:
        point["omp_num_threads"] = 64

    print("flops for this setting =", run(point))
