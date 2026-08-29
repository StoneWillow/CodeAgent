"""简单命令行计算器：支持加减乘除、幂、取余运算。"""


def calculate(a: float, op: str, b: float) -> float:
    """执行单个二元运算。"""
    if op == "+":
        return a + b
    elif op == "-":
        return a - b
    elif op == "*":
        return a * b
    elif op == "/":
        if b == 0:
            raise ZeroDivisionError("除数不能为 0")
        return a / b
    elif op == "**":
        return a ** b
    elif op == "%":
        if b == 0:
            raise ZeroDivisionError("取余的除数不能为 0")
        return a % b
    else:
        raise ValueError(f"不支持的运算符: {op}")


def main():
    print("===== 简单计算器 =====")
    print("支持的运算符: + - * / ** %")
    print("输入格式示例: 3 + 5   或输入 q 退出\n")

    while True:
        try:
            expr = input(">>> ").strip()
        except EOFError:
            print("\n再见！")
            break

        try:
            if expr.lower() in ("q", "quit", "exit"):
                print("再见！")
                break
            if not expr:
                continue

            parts = expr.split()
            if len(parts) != 3:
                print("格式错误！请输入: 数字 运算符 数字")
                continue

            a = float(parts[0])
            op = parts[1]
            b = float(parts[2])

            result = calculate(a, op, b)
            print(f"{a:g} {op} {b:g} = {result:g}")
        except ValueError as e:
            print(f"输入错误: {e}")
        except ZeroDivisionError as e:
            print(f"数学错误: {e}")
        except KeyboardInterrupt:
            print("\n再见！")
            break


if __name__ == "__main__":
    main()
